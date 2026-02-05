"""
RAG context retrieval for the explanation feature.

Allowed data sources (read-only):
  - Match metadata and events (MatchRepository, analytics)
  - Player context (rankings_db; id, name, country, rank, points)
  - Static domain knowledge (table tennis rules, scoring description)

Disallowed: simulation internals, random seeds, any write-capable API.
All functions are side-effect free and unit testable.
"""
from __future__ import annotations

import json
from typing import Any

from backend.analytics import compute_match_analytics
from backend.persistence.repositories import MatchRepository
from backend.rankings_db import get_player


# ---------- Static domain knowledge (table tennis rules, scoring) ----------
RULES_CONTENT = """
Table tennis match rules (ITTF-style):
- A match is played best of 3, 5, or 7 sets (commonly best of 5 or 7).
- A set is won by the first player to reach 11 points, with a margin of at least 2 (e.g. 11-9, 12-10).
- Points are scored on every rally (no "deuce" exception; play continues until 2-point margin).
- Service alternates every 2 points; at 10-10 (deuce) service alternates every point.
- The winner of the match is the first to win a majority of sets (e.g. 3 sets in a best-of-5).

Fantasy scoring (for context only; the simulation does not use this for match outcome):
- Match win/loss, set wins/losses, and point differential contribute to fantasy points.
- Comeback sets (winning a set after trailing by 4+ points), deciding set wins, and streak-related events can add or subtract points.
- Shot-type bonuses (forehand/backhand/service winners, unforced errors) are factored in.
"""


def get_match_analytics(conn: Any, match_id: str) -> dict[str, Any] | None:
    """
    Return deterministic analytics for the match (outcome, stats, fantasy scores).
    Returns None if match not found or has no events.
    """
    match_repo = MatchRepository()
    match = match_repo.get(conn, match_id)
    if match is None:
        return None
    events = []
    if match.events_json:
        events = json.loads(match.events_json)
    return compute_match_analytics(match, events)


def get_match_summary(conn: Any, match_id: str) -> dict[str, Any] | None:
    """
    Return match metadata only: id, teams, players, winner, set score, best_of, created_at.
    No event data. Returns None if match not found.
    """
    match_repo = MatchRepository()
    match = match_repo.get(conn, match_id)
    if match is None:
        return None
    return {
        "id": match.id,
        "team_a_id": match.team_a_id,
        "team_b_id": match.team_b_id,
        "player_a_id": match.player_a_id,
        "player_b_id": match.player_b_id,
        "winner_id": match.winner_id,
        "sets_a": match.sets_a,
        "sets_b": match.sets_b,
        "best_of": match.best_of,
        "created_at": match.created_at.isoformat(),
    }


def get_player_context(conn: Any, player_ids: list[str]) -> list[dict[str, Any]]:
    """
    Return structured player info (id, name, country, gender, rank, points) for each id.
    Missing players are omitted; order follows input order where present.
    """
    out: list[dict[str, Any]] = []
    for pid in player_ids:
        row = get_player(conn, pid)
        if row is None:
            continue
        out.append({
            "id": row.id,
            "name": row.name,
            "country": row.country,
            "gender": row.gender,
            "rank": row.rank,
            "points": row.points,
        })
    return out


def get_rules_context() -> str:
    """
    Return static domain knowledge: table tennis rules and scoring explanation.
    No I/O; same content every call.
    """
    return RULES_CONTENT.strip()
