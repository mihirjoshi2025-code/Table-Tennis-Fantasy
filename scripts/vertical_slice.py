#!/usr/bin/env python3
"""
Vertical slice: Create team → Simulate match → Persist → Retrieve.
Run from project root: python3 scripts/vertical_slice.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.persistence import init_db, get_connection, UserRepository, TeamRepository, MatchRepository
from backend.persistence.db import get_db_path, set_db_path
from backend.rankings_db import list_players_by_gender, get_player, build_profile_store_for_match
from backend.scoring import aggregate_stats_from_events, compute_fantasy_score
from backend.simulation.schemas import MatchConfig
from backend.simulation.orchestrator import MatchOrchestrator, sets_to_win_match


def main() -> None:
    # Use data/vertical_slice.db for demo (distinct from app.db)
    db_path = PROJECT_ROOT / "data" / "vertical_slice.db"
    set_db_path(db_path)
    init_db(db_path=db_path, rankings_path=PROJECT_ROOT / "data" / "rankings.json")

    conn = get_connection()
    try:
        user_repo = UserRepository()
        team_repo = TeamRepository()
        match_repo = MatchRepository()

        # 1. Ensure user exists
        user_id = "vertical-slice-user"
        user = user_repo.get(conn, user_id)
        if user is None:
            user = user_repo.create(conn, name="Slice Demo User", id=user_id)
            print(f"Created user: {user.id}")

        # 2. Create two teams
        players_men = list_players_by_gender(conn, "men", limit=10)
        player_ids = [p.id for p in players_men[:6]]
        team_a = team_repo.create(conn, user_id, "Champions", player_ids[:3])
        team_b = team_repo.create(conn, user_id, "Underdogs", player_ids[3:6])
        print(f"Created team A: {team_a.name} (id={team_a.id})")
        print(f"Created team B: {team_b.name} (id={team_b.id})")

        # 3. Simulate match between teams (first player per team)
        player_a_id = team_repo.get_players(conn, team_a.id)[0]
        player_b_id = team_repo.get_players(conn, team_b.id)[0]
        seed = 99999
        best_of = 5

        store = build_profile_store_for_match(conn, player_a_id, player_b_id)
        match_id = f"slice-{team_a.id[:8]}-{team_b.id[:8]}-{seed}"
        config = MatchConfig(
            match_id=match_id,
            player_a_id=player_a_id,
            player_b_id=player_b_id,
            seed=seed,
            best_of=best_of,
        )
        orch = MatchOrchestrator(config, store)
        events = list(orch.run())

        sets_needed = sets_to_win_match(best_of)
        last = events[-1]
        sets_a, sets_b = last.set_scores_after[0], last.set_scores_after[1]
        winner_id = player_a_id if sets_a >= sets_needed else player_b_id

        def _ev_to_dict(e):
            return {
                "point_index": e.point_index,
                "set_index": e.set_index,
                "score_after": list(e.score_after),
                "set_scores_after": list(e.set_scores_after),
                "outcome": {"winner_id": e.outcome.winner_id, "shot_type": e.outcome.shot_type},
            }

        events_json = json.dumps([_ev_to_dict(e) for e in events])

        match = match_repo.create(
            conn,
            team_a_id=team_a.id,
            team_b_id=team_b.id,
            player_a_id=player_a_id,
            player_b_id=player_b_id,
            winner_id=winner_id,
            sets_a=sets_a,
            sets_b=sets_b,
            best_of=best_of,
            seed=seed,
            events_json=events_json,
            id=match_id,
        )
        print(f"Simulated and persisted match: {match.id}")
        print(f"  Result: {sets_a}-{sets_b} (winner: {winner_id})")

        # Fantasy scores
        stats_a, stats_b = aggregate_stats_from_events(
            events, winner_id=winner_id,
            player_a_id=player_a_id, player_b_id=player_b_id,
            best_of=best_of,
        )
        print(f"  Fantasy: {player_a_id} = {compute_fantasy_score(stats_a):.1f}, {player_b_id} = {compute_fantasy_score(stats_b):.1f}")

        # 4. Retrieve match
        retrieved = match_repo.get(conn, match_id)
        assert retrieved is not None
        print(f"Retrieved match: id={retrieved.id}, sets={retrieved.sets_a}-{retrieved.sets_b}")

        print("\nVertical slice complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
