"""
Live league match simulation: runs deterministic team match once, then emits
partial scores over ~4–5 minutes (each of the 7 slot "games" over 30–45s) for
real-time UX. Final totals match simulation. Keeps live logic separate from
final scoring; runs in background task to avoid blocking.
"""
from __future__ import annotations

import asyncio
import random
import sqlite3
from typing import Any, Callable

from backend.persistence.repositories import LeagueMatchRepository
from backend.services.simulation_service import run_team_match_simulation

# Each of the 7 head-to-head slot "games" runs ~35s so users can follow live summaries and momentum.
SECONDS_PER_GAME = 35
NUM_SLOTS = 7
LIVE_DURATION_SECONDS = NUM_SLOTS * SECONDS_PER_GAME  # ~245s total
LIVE_STEP_SECONDS = 2.5
LIVE_STEP_JITTER = 0.3


def run_live_league_match(
    conn: sqlite3.Connection,
    league_match_id: str,
    seed: int | None = None,
    on_tick: Callable[[float, float, float, list[dict], bool], None] | None = None,
) -> dict[str, Any]:
    """
    Run full simulation, then invoke on_tick with discrete slot-by-slot updates (no interpolation).
    Does not persist; caller must persist and set status=completed.
    Returns final result dict (home_score, away_score, highlights, ...).
    """
    league_match_repo = LeagueMatchRepository()
    m = league_match_repo.get(conn, league_match_id)
    if m is None:
        raise ValueError(f"League match not found: {league_match_id}")
    if m.away_team_id is None:
        return {"home_score": 0.0, "away_score": 0.0, "highlights": [], "explanation": "Bye"}
    result = run_team_match_simulation(
        conn, m.home_team_id, m.away_team_id, seed=seed, best_of=5
    )
    highlights = result.get("highlights", [])
    cumul_home, cumul_away = _cumulative_scores_from_highlights(highlights)
    if on_tick:
        on_tick(0.0, 0.0, 0.0, [], False)
    for k in range(len(highlights)):
        elapsed = (k + 1) * SECONDS_PER_GAME
        home_score = cumul_home[k]
        away_score = cumul_away[k]
        highlights_so_far = highlights[: k + 1]
        done = k == len(highlights) - 1
        if on_tick:
            on_tick(elapsed, home_score, away_score, highlights_so_far, done)
    return result


def _cumulative_scores_from_highlights(highlights: list[dict]) -> tuple[list[float], list[float]]:
    """Build cumulative home/away scores after each slot. Append-only; no interpolation."""
    cumul_home: list[float] = []
    cumul_away: list[float] = []
    h_tot, a_tot = 0.0, 0.0
    for hl in highlights:
        h_tot += float(hl.get("points_home", 0))
        a_tot += float(hl.get("points_away", 0))
        cumul_home.append(round(h_tot, 1))
        cumul_away.append(round(a_tot, 1))
    return cumul_home, cumul_away


async def run_live_league_match_with_delays(
    get_conn: Callable[[], sqlite3.Connection],
    league_match_id: str,
    seed: int | None = None,
    on_tick_async: Callable[[float, float, float, list[dict], bool], Any] | None = None,
) -> dict[str, Any]:
    """
    Run full simulation in thread (non-blocking), then emit discrete slot-by-slot
    updates. Scores are append-only: each tick sends cumulative score after that slot
    completes. No interpolation; no retroactive changes.
    """
    import concurrent.futures

    def get_conn_sync():
        return get_conn()

    def run_sim():
        conn = get_conn_sync()
        league_match_repo = LeagueMatchRepository()
        m = league_match_repo.get(conn, league_match_id)
        if m is None:
            raise ValueError(f"League match not found: {league_match_id}")
        if m.away_team_id is None:
            return {"home_score": 0.0, "away_score": 0.0, "highlights": [], "explanation": "Bye"}
        return run_team_match_simulation(
            conn, m.home_team_id, m.away_team_id, seed=seed, best_of=5
        )

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        result = await loop.run_in_executor(ex, run_sim)

    if result.get("away_score") == 0.0 and result.get("explanation") == "Bye":
        return result

    highlights = result.get("highlights", [])
    cumul_home, cumul_away = _cumulative_scores_from_highlights(highlights)

    # Initial tick is sent by API _run_live_task before calling this, so late join gets state immediately.

    # Discrete slot-by-slot: wait SECONDS_PER_GAME, then emit cumulative score for that slot.
    for k in range(len(highlights)):
        await asyncio.sleep(SECONDS_PER_GAME)
        elapsed = (k + 1) * SECONDS_PER_GAME
        home_score = cumul_home[k]
        away_score = cumul_away[k]
        highlights_so_far = highlights[: k + 1]
        done = k == len(highlights) - 1
        if on_tick_async:
            if asyncio.iscoroutinefunction(on_tick_async):
                await on_tick_async(elapsed, home_score, away_score, highlights_so_far, done)
            else:
                on_tick_async(elapsed, home_score, away_score, highlights_so_far, done)

    return result
