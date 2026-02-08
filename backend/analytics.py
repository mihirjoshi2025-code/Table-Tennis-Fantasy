"""
Deterministic match analytics.
Read-only: consumes match metadata and event data, returns structured stats.
Used by GET /analysis/match/{id} and by the explanation RAG retrieval layer.
No simulation, no persistence, no LLM.
"""
from __future__ import annotations

import json
from typing import Any

from backend.models import Match
from backend.scoring import (
    aggregate_stats_from_events,
    compute_fantasy_score,
)


def _event_server(e: Any) -> str:
    return e.get("server_id", "") if hasattr(e, "get") and callable(getattr(e, "get", None)) else getattr(e, "server_id", "")


def _event_winner(e: Any) -> str:
    o = e.get("outcome", {}) if hasattr(e, "get") and callable(getattr(e, "get", None)) else getattr(e, "outcome", None)
    if hasattr(o, "winner_id"):
        return o.winner_id
    return (o or {}).get("winner_id", "")


def _event_rally_length(e: Any) -> int:
    if hasattr(e, "get") and callable(getattr(e, "get", None)):
        return e.get("rally_length", 0)
    return getattr(e, "rally_length", 0)


def _compute_rally_and_serve_stats(
    events: list[Any], player_a_id: str, player_b_id: str
) -> dict[str, Any]:
    """Derive rally and serve stats from events. No I/O."""
    total_points = len(events)
    if total_points == 0:
        return {
            "longest_rally": 0,
            "avg_rally_length": 0.0,
            "serve_win_pct_a": None,
            "serve_win_pct_b": None,
            "estimated_duration_seconds": 0,
        }
    rally_lengths = [_event_rally_length(e) for e in events]
    longest_rally = max(rally_lengths)
    avg_rally_length = round(sum(rally_lengths) / total_points, 1)
    # Serve: points won when serving
    serve_points_a = serve_won_a = 0
    serve_points_b = serve_won_b = 0
    for e in events:
        server = _event_server(e)
        winner = _event_winner(e)
        if server == player_a_id:
            serve_points_a += 1
            if winner == player_a_id:
                serve_won_a += 1
        elif server == player_b_id:
            serve_points_b += 1
            if winner == player_b_id:
                serve_won_b += 1
    serve_win_pct_a = round(100 * serve_won_a / serve_points_a, 1) if serve_points_a else None
    serve_win_pct_b = round(100 * serve_won_b / serve_points_b, 1) if serve_points_b else None
    # ~25 seconds per point for table tennis (simulated)
    estimated_duration_seconds = total_points * 25
    return {
        "longest_rally": longest_rally,
        "avg_rally_length": avg_rally_length,
        "serve_win_pct_a": serve_win_pct_a,
        "serve_win_pct_b": serve_win_pct_b,
        "estimated_duration_seconds": estimated_duration_seconds,
    }


def _stats_to_dict(stats: Any) -> dict[str, Any]:
    """Convert MatchStats to a JSON-friendly dict for API/context."""
    return {
        "player_id": stats.player_id,
        "is_winner": stats.is_winner,
        "sets_won": stats.sets_won,
        "sets_lost": stats.sets_lost,
        "best_of": stats.best_of,
        "net_point_differential": stats.net_point_differential,
        "comeback_sets": stats.comeback_sets,
        "won_deciding_set": stats.won_deciding_set,
        "streak_breaks": stats.streak_breaks,
        "streaks_3_plus": stats.streaks_3_plus,
        "forehand_winners": stats.forehand_winners,
        "backhand_winners": stats.backhand_winners,
        "service_winners": stats.service_winners,
        "unforced_errors": stats.unforced_errors,
    }


def _event_shot_type(e: Any) -> str:
    o = e.get("outcome", {}) if hasattr(e, "get") and callable(getattr(e, "get", None)) else getattr(e, "outcome", None)
    if hasattr(o, "shot_type"):
        return (o.shot_type or "").lower()
    return ((o or {}).get("shot_type") or "").lower()


def compute_slot_tt_momentum_and_stats(
    events: list[Any], player_a_id: str, player_b_id: str, winner_id: str
) -> dict[str, Any]:
    """
    From point events, compute: TT momentum series (time_seconds vs cumulative table tennis points),
    serve stats, shot breakdown. Used for league match slot_data and game pages.
    """
    momentum_series: list[dict[str, Any]] = []
    cumul_a, cumul_b = 0, 0
    SECONDS_PER_POINT = 25
    for i, ev in enumerate(events):
        w = _event_winner(ev)
        if w == player_a_id:
            cumul_a += 1
        elif w == player_b_id:
            cumul_b += 1
        t = i * SECONDS_PER_POINT
        momentum_series.append({
            "point_index": i + 1,
            "time_seconds": t,
            "cumul_tt_a": cumul_a,
            "cumul_tt_b": cumul_b,
        })
    rally_serve = _compute_rally_and_serve_stats(events, player_a_id, player_b_id)
    stats_a, stats_b = aggregate_stats_from_events(
        events, winner_id=winner_id,
        player_a_id=player_a_id, player_b_id=player_b_id,
        best_of=5,
    )
    return {
        "momentum_series": momentum_series,
        "total_points": len(events),
        "longest_rally": rally_serve["longest_rally"],
        "avg_rally_length": rally_serve["avg_rally_length"],
        "serve_win_pct_a": rally_serve["serve_win_pct_a"],
        "serve_win_pct_b": rally_serve["serve_win_pct_b"],
        "estimated_duration_seconds": rally_serve["estimated_duration_seconds"],
        "player_a_stats": _stats_to_dict(stats_a),
        "player_b_stats": _stats_to_dict(stats_b),
    }


def compute_league_match_slot_data(slot_details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    From simulation slot_details (each with events_json, player_a_id, player_b_id, winner_id),
    build slot_data: per-slot TT momentum, analytics, and summary for API/frontend.
    """
    slot_data: list[dict[str, Any]] = []
    for slot_dict in slot_details:
        events_json = slot_dict.get("events_json")
        if not events_json:
            slot_data.append({
                "slot": slot_dict.get("slot", len(slot_data) + 1),
                "momentum_series": [],
                "total_points": 0,
                "player_a_stats": None,
                "player_b_stats": None,
                "serve_win_pct_a": None,
                "serve_win_pct_b": None,
            })
            continue
        events = json.loads(events_json)
        player_a_id = slot_dict.get("player_a_id", "")
        player_b_id = slot_dict.get("player_b_id", "")
        winner_id = slot_dict.get("winner_id", player_a_id)
        computed = compute_slot_tt_momentum_and_stats(
            events, player_a_id, player_b_id, winner_id
        )
        slot_data.append({
            "slot": slot_dict.get("slot", len(slot_data) + 1),
            "match_id": slot_dict.get("match_id"),
            "home_player_id": player_a_id,
            "away_player_id": player_b_id,
            "winner_id": winner_id,
            **computed,
        })
    return slot_data


def compute_total_match_momentum(slot_data: list[dict[str, Any]], seconds_per_slot: float = 35.0) -> list[dict[str, Any]]:
    """
    Concatenate per-slot TT momentum into one series for the whole match.
    Time offset: slot 1 = 0..T1, slot 2 = T1..T2, etc. Cumulative TT points add across slots.
    """
    total: list[dict[str, Any]] = []
    time_offset = 0.0
    cumul_home = 0
    cumul_away = 0
    for s in slot_data:
        series = s.get("momentum_series") or []
        if not series:
            time_offset += seconds_per_slot
            total.append({
                "time_seconds": round(time_offset, 1),
                "cumul_tt_home": cumul_home,
                "cumul_tt_away": cumul_away,
            })
            continue
        for pt in series:
            t = time_offset + pt.get("time_seconds", 0)
            # In slot, player_a = home, player_b = away; add to running totals
            total.append({
                "time_seconds": round(t, 1),
                "cumul_tt_home": cumul_home + pt.get("cumul_tt_a", 0),
                "cumul_tt_away": cumul_away + pt.get("cumul_tt_b", 0),
            })
        last = series[-1]
        cumul_home += last.get("cumul_tt_a", 0)
        cumul_away += last.get("cumul_tt_b", 0)
        time_offset += (last.get("time_seconds", 0) + 25)
    return total


def compute_match_analytics(match: Match, events: list[Any]) -> dict[str, Any]:
    """
    Compute structured analytics from a match and its point events.
    Pure function: no I/O, no side effects.
    """
    if not events:
        return {
            "match_id": match.id,
            "outcome": {
                "winner_id": match.winner_id,
                "sets_a": match.sets_a,
                "sets_b": match.sets_b,
                "best_of": match.best_of,
            },
            "player_a_id": match.player_a_id,
            "player_b_id": match.player_b_id,
            "player_a_stats": None,
            "player_b_stats": None,
            "fantasy_scores": {},
        }
    stats_a, stats_b = aggregate_stats_from_events(
        events,
        winner_id=match.winner_id,
        player_a_id=match.player_a_id,
        player_b_id=match.player_b_id,
        best_of=match.best_of,
    )
    fantasy_a = compute_fantasy_score(stats_a)
    fantasy_b = compute_fantasy_score(stats_b)
    rally_serve = _compute_rally_and_serve_stats(
        events, match.player_a_id, match.player_b_id
    )
    return {
        "match_id": match.id,
        "outcome": {
            "winner_id": match.winner_id,
            "sets_a": match.sets_a,
            "sets_b": match.sets_b,
            "best_of": match.best_of,
        },
        "player_a_id": match.player_a_id,
        "player_b_id": match.player_b_id,
        "player_a_stats": _stats_to_dict(stats_a),
        "player_b_stats": _stats_to_dict(stats_b),
        "fantasy_scores": {
            match.player_a_id: round(fantasy_a, 1),
            match.player_b_id: round(fantasy_b, 1),
        },
        "total_points_played": len(events),
        "longest_rally": rally_serve["longest_rally"],
        "avg_rally_length": rally_serve["avg_rally_length"],
        "serve_win_pct_a": rally_serve["serve_win_pct_a"],
        "serve_win_pct_b": rally_serve["serve_win_pct_b"],
        "estimated_duration_seconds": rally_serve["estimated_duration_seconds"],
    }
