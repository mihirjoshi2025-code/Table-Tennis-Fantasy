"""
Pure team-vs-team simulation: no persistence, no UI.
Callable by league week execution logic or by API for user-triggered simulate.
Returns scores, winner, explanation; optionally slot_details for persistence.
"""
from __future__ import annotations

import json
import random
import sqlite3
from typing import Any

from backend.rankings_db import build_profile_store_for_match, get_player
from backend.persistence.repositories import TeamRepository
from backend.roles import parse_role, apply_role_to_fantasy_score, RoleContext
from backend.scoring import aggregate_stats_from_events, compute_fantasy_score
from backend.simulation.persistence import event_to_dict
from backend.simulation.schemas import MatchConfig
from backend.simulation.orchestrator import MatchOrchestrator, sets_to_win_match

TEAM_ACTIVE = 7
CAPTAIN_BONUS_MULTIPLIER = 1.5


def run_team_match_simulation(
    conn: sqlite3.Connection,
    home_team_id: str,
    away_team_id: str,
    seed: int | None = None,
    best_of: int = 5,
) -> dict[str, Any]:
    """
    Run a 7v7 team match simulation. Does not persist anything.
    Returns home_score, away_score, winner_team_id (home or away), and explanation/highlights.
    Callable by league week execution; not for direct user-triggered use.
    """
    seed_base = seed if seed is not None else random.randint(1, 2**31 - 1)
    team_repo = TeamRepository()

    home_team = team_repo.get(conn, home_team_id)
    away_team = team_repo.get(conn, away_team_id)
    if home_team is None:
        raise ValueError(f"Team not found: {home_team_id}")
    if away_team is None:
        raise ValueError(f"Team not found: {away_team_id}")
    if home_team.gender != away_team.gender:
        raise ValueError("Teams must be the same gender (men vs men or women vs women)")

    active_home = team_repo.get_active_player_ids(conn, home_team_id)
    active_away = team_repo.get_active_player_ids(conn, away_team_id)
    if len(active_home) != TEAM_ACTIVE:
        raise ValueError(f"Home team must have exactly {TEAM_ACTIVE} active players (slots 1-7)")
    if len(active_away) != TEAM_ACTIVE:
        raise ValueError(f"Away team must have exactly {TEAM_ACTIVE} active players (slots 1-7)")

    captain_home = team_repo.get_captain_id(conn, home_team_id)
    captain_away = team_repo.get_captain_id(conn, away_team_id)
    roster_home = team_repo.get_active_roster_with_roles(conn, home_team_id)
    roster_away = team_repo.get_active_roster_with_roles(conn, away_team_id)

    score_home = 0.0
    score_away = 0.0
    highlights: list[dict[str, Any]] = []
    slot_details: list[dict[str, Any]] = []

    for i in range(TEAM_ACTIVE):
        player_h_id = active_home[i]
        player_a_id = active_away[i]
        role_h = parse_role(roster_home[i][1]) if i < len(roster_home) else None
        role_a = parse_role(roster_away[i][1]) if i < len(roster_away) else None
        slot_seed = seed_base + i
        match_id = f"sim-{home_team_id[:8]}-{away_team_id[:8]}-{slot_seed}"
        store = build_profile_store_for_match(conn, player_h_id, player_a_id)
        config = MatchConfig(
            match_id=match_id,
            player_a_id=player_h_id,
            player_b_id=player_a_id,
            seed=slot_seed,
            best_of=best_of,
        )
        orch = MatchOrchestrator(config, store)
        events = list(orch.run())
        if not events:
            raise RuntimeError(f"Simulation produced no events for slot {i+1}")

        sets_needed = sets_to_win_match(best_of)
        last = events[-1]
        sets_h, sets_a = last.set_scores_after[0], last.set_scores_after[1]
        winner_id = player_h_id if sets_h >= sets_needed else player_a_id
        stats_h, stats_a = aggregate_stats_from_events(
            events, winner_id=winner_id,
            player_a_id=player_h_id, player_b_id=player_a_id,
            best_of=best_of,
        )
        raw_fantasy_h = compute_fantasy_score(stats_h)
        raw_fantasy_a = compute_fantasy_score(stats_a)

        # Role handler: apply role effects before captain bonus (keeps simulation loop role-agnostic)
        ctx_h = RoleContext(
            slot_index=i,
            total_slots=TEAM_ACTIVE,
            is_winner=(winner_id == player_h_id),
            team_side="home",
            cumulative_team_score_before=score_home,
            seed=slot_seed,
        )
        ctx_a = RoleContext(
            slot_index=i,
            total_slots=TEAM_ACTIVE,
            is_winner=(winner_id == player_a_id),
            team_side="away",
            cumulative_team_score_before=score_away,
            seed=slot_seed,
        )
        fantasy_h, log_h = apply_role_to_fantasy_score(raw_fantasy_h, player_h_id, role_h, ctx_h)
        fantasy_a, log_a = apply_role_to_fantasy_score(raw_fantasy_a, player_a_id, role_a, ctx_a)
        role_log_entries: list[dict[str, Any]] = [e.to_dict() for e in log_h + log_a]

        if captain_home == player_h_id:
            fantasy_h *= CAPTAIN_BONUS_MULTIPLIER
        if captain_away == player_a_id:
            fantasy_a *= CAPTAIN_BONUS_MULTIPLIER
        score_home += fantasy_h
        score_away += fantasy_a

        events_json = json.dumps([event_to_dict(e) for e in events])
        slot_details.append({
            "match_id": match_id,
            "player_a_id": player_h_id,
            "player_b_id": player_a_id,
            "winner_id": winner_id,
            "sets_a": sets_h,
            "sets_b": sets_a,
            "events_json": events_json,
            "points_a": round(fantasy_h, 1),
            "points_b": round(fantasy_a, 1),
            "seed": slot_seed,
            "role_log": role_log_entries,
        })

        p_h = get_player(conn, player_h_id)
        p_a = get_player(conn, player_a_id)
        highlights.append({
            "slot": i + 1,
            "home_player_id": player_h_id,
            "away_player_id": player_a_id,
            "home_player_name": p_h.name if p_h else player_h_id,
            "away_player_name": p_a.name if p_a else player_a_id,
            "points_home": round(fantasy_h, 1),
            "points_away": round(fantasy_a, 1),
            "winner_id": winner_id,
            "role_log": role_log_entries,
        })

    winner_team_id: str | None
    if score_home > score_away:
        winner_team_id = home_team_id
    elif score_away > score_home:
        winner_team_id = away_team_id
    else:
        winner_team_id = None

    # Short explanation string for storage in league_match.simulation_log
    explanation = f"Home {round(score_home, 1)} - Away {round(score_away, 1)}. Winner: {winner_team_id or 'tie'}."

    return {
        "home_score": round(score_home, 1),
        "away_score": round(score_away, 1),
        "winner_team_id": winner_team_id,
        "explanation": explanation,
        "highlights": highlights,
        "slot_details": slot_details,
        "seed_base": seed_base,
    }
