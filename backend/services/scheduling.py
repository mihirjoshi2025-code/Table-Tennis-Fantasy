"""
Deterministic round-robin schedule generation for leagues.

Round-robin is used so every team plays every other team exactly once; season length
is N-1 weeks (N even) or N weeks (N odd). Each team plays at most one match per week.

BYE handling: when the number of teams is odd, we add a virtual BYE. Each week one
team is paired with BYE (away_team_id = None) and does not play. This keeps the
schedule uniform and supports 4–20 teams without code changes.

Uses the circle method: fix first slot, rotate others each week. Same team list
ordering yields the same schedule (deterministic for persistence).
"""
from __future__ import annotations

from typing import Any

# Sentinel for bye when number of teams is odd
BYE = "BYE"


def round_robin_pairings(team_ids: list[str]) -> list[tuple[int, str, str | None]]:
    """
    Generate round-robin pairings: (week_number, home_team_id, away_team_id).
    away_team_id is None when home_team_id has a bye (odd number of teams).
    Deterministic: same team list => same schedule.
    """
    if not team_ids:
        return []
    ids = list(team_ids)
    n = len(ids)
    if n % 2 == 1:
        ids.append(BYE)
    N = len(ids)  # N is even
    weeks = N - 1
    result: list[tuple[int, str, str | None]] = []
    # Circle method: indices 0..N-1. Fix 0, rotate 1..N-1 each week.
    # Week 0: pair (0, N-1), (1, N-2), (2, N-3), ...
    # Week 1: rotate so slot 0 stays; new order [0, N-1, 1, 2, ..., N-2]; pair (0,N-1), (1,N-2), ...
    order = list(range(N))
    for week in range(weeks):
        # Pair order[0] with order[N-1], order[1] with order[N-2], ...
        for i in range(N // 2):
            a, b = order[i], order[N - 1 - i]
            home_id = ids[a]
            away_id = ids[b]
            if home_id == BYE or away_id == BYE:
                if home_id == BYE:
                    home_id, away_id = away_id, None
                else:
                    away_id = None
            if away_id is not None:
                result.append((week + 1, home_id, away_id))
            else:
                result.append((week + 1, home_id, None))
        # Rotate: keep 0, then order[N-1], order[1], order[2], ..., order[N-2]
        order = [order[0]] + [order[N - 1]] + order[1 : N - 1]
    return result


def generate_league_schedule(team_ids: list[str]) -> list[dict[str, Any]]:
    """
    Return list of fixtures: { "week_number": int, "home_team_id": str, "away_team_id": str | None }.
    away_team_id None = bye. Deterministic; no duplicate matchups; max one game per team per week.
    """
    pairings = round_robin_pairings(team_ids)
    return [
        {"week_number": w, "home_team_id": h, "away_team_id": a}
        for w, h, a in pairings
    ]
