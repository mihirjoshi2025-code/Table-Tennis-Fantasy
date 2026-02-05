"""
Deterministic match analytics.
Read-only: consumes match metadata and event data, returns structured stats.
Used by GET /analysis/match/{id} and by the explanation RAG retrieval layer.
No simulation, no persistence, no LLM.
"""
from __future__ import annotations

from typing import Any

from backend.models import Match
from backend.scoring import (
    aggregate_stats_from_events,
    compute_fantasy_score,
)


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
    }
