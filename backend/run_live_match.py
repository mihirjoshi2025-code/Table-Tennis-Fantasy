"""
Run a simulated match between two random same-gender players from the rankings DB.
Simulation produces point events in real time; each point is fed to the scoring
engine and the live score is printed in the terminal as if it were a real game.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

# Run from project root: python -m backend.run_live_match
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.rankings_db import (
    init_db,
    list_players_by_gender,
    build_profile_store_for_match,
)
from backend.scoring import aggregate_stats_from_events, compute_fantasy_score
from backend.simulation.schemas import MatchConfig
from backend.simulation.orchestrator import MatchOrchestrator, sets_to_win_match
from backend.simulation.emitter import EmitterConfig, SyncEmitter


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_db(rankings_path: Path, db_path: Path) -> None:
    init_db(db_path, rankings_path)


def _pick_two_same_gender(conn, gender: str):
    players = list_players_by_gender(conn, gender)
    if len(players) < 2:
        raise SystemExit("Need at least 2 players in rankings for that gender.")
    two = random.sample(players, 2)
    return two[0], two[1]


def _print_live_score(event, name_a: str, name_b: str, player_a_id: str, player_b_id: str) -> None:
    """Print current set scores and game score after each point."""
    sa, sb = event.set_scores_after[0], event.set_scores_after[1]
    ga, gb = event.score_after[0], event.score_after[1]
    winner_name = name_a if event.outcome.winner_id == player_a_id else name_b
    shot = event.outcome.shot_type
    print(f"  Point → {winner_name} wins ({shot})   Sets: {sa}-{sb}   Game: {ga}-{gb}")


def _print_final(
    events: list,
    winner_id: str,
    player_a_id: str,
    player_b_id: str,
    name_a: str,
    name_b: str,
    best_of: int,
) -> None:
    """Print match result and fantasy scores."""
    if not events:
        return
    last = events[-1]
    sets_a, sets_b = last.set_scores_after[0], last.set_scores_after[1]
    winner_name = name_a if winner_id == player_a_id else name_b
    loser_name = name_b if winner_id == player_a_id else name_a
    print()
    print("=" * 60)
    print(f"  MATCH RESULT: {winner_name} def. {loser_name}  {sets_a}-{sets_b}")
    print("=" * 60)
    stats_a, stats_b = aggregate_stats_from_events(
        events,
        winner_id=winner_id,
        player_a_id=player_a_id,
        player_b_id=player_b_id,
        best_of=best_of,
    )
    score_a = compute_fantasy_score(stats_a)
    score_b = compute_fantasy_score(stats_b)
    print(f"  Fantasy score: {name_a} {score_a:.1f}  |  {name_b} {score_b:.1f}")
    print()


def run(
    seed: int | None = None,
    gender: str = "men",
    fast: bool = False,
    rankings_path: Path | None = None,
    db_path: Path | None = None,
) -> None:
    if seed is None:
        seed = random.randint(1, 2**31 - 1)
    root = _project_root()
    rankings_path = rankings_path or root / "data" / "rankings.json"
    db_path = db_path or root / "data" / "rankings.db"
    if not rankings_path.exists():
        raise SystemExit(f"Rankings file not found: {rankings_path}")
    _ensure_db(rankings_path, db_path)

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        p1, p2 = _pick_two_same_gender(conn, gender)
        player_a_id, player_b_id = p1.id, p2.id
        name_a, name_b = p1.name, p2.name
        store = build_profile_store_for_match(conn, player_a_id, player_b_id)
    finally:
        conn.close()

    best_of = 5
    sets_needed = sets_to_win_match(best_of)
    config = MatchConfig(
        match_id=f"live-{player_a_id}-{player_b_id}-{seed}",
        player_a_id=player_a_id,
        player_b_id=player_b_id,
        seed=seed,
        best_of=best_of,
    )
    orch = MatchOrchestrator(config, store)
    events: list = []

    def on_point(ev):
        events.append(ev)
        _print_live_score(ev, name_a, name_b, player_a_id, player_b_id)

    emitter_cfg = EmitterConfig(
        min_seconds_per_point=0.3 if fast else 0.8,
        max_seconds_per_point=0.5 if fast else 1.5,
        pause_between_sets_seconds=0 if fast else 3.0,
        fast_forward=fast,
    )
    emitter = SyncEmitter(emitter_cfg)
    print(f"\n  {name_a} ({p1.country})  vs  {name_b} ({p2.country})  [best of {best_of}, seed={seed}]")
    print("  " + "-" * 56)
    event_iter = orch.run(on_point=None)
    emitter.emit_stream(event_iter, on_event=on_point)
    if not events:
        return
    last = events[-1]
    winner_id = config.player_a_id if last.set_scores_after[0] >= sets_needed else config.player_b_id
    _print_final(events, winner_id, player_a_id, player_b_id, name_a, name_b, best_of)


def main():
    parser = argparse.ArgumentParser(description="Run a live simulated match with real-time scoring.")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    parser.add_argument("--gender", choices=("men", "women"), default="men", help="Player gender")
    parser.add_argument("--fast", action="store_true", help="Minimal delay between points")
    args = parser.parse_args()
    run(seed=args.seed, gender=args.gender, fast=args.fast)


if __name__ == "__main__":
    main()
