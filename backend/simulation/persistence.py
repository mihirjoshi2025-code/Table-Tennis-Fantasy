"""
Persistence, Replay & Diagnostics: store event log + seed + profile versions
for exact replay; store per-match and per-player summaries for backtesting.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .schemas import PointEvent, MatchConfig


@dataclass
class ReplayMetadata:
    """Enough to replay a match exactly."""
    match_id: str
    seed: int
    config: dict[str, Any]
    profile_versions: dict[str, str]
    event_count: int


def event_to_dict(e: PointEvent) -> dict[str, Any]:
    """PointEvent to JSON-serializable dict."""
    return {
        "match_id": e.match_id,
        "point_index": e.point_index,
        "set_index": e.set_index,
        "game_index": e.game_index,
        "score_before": list(e.score_before),
        "score_after": list(e.score_after),
        "set_scores_before": list(e.set_scores_before),
        "set_scores_after": list(e.set_scores_after),
        "server_id": e.server_id,
        "outcome": {
            "winner_id": e.outcome.winner_id,
            "loser_id": e.outcome.loser_id,
            "shot_type": e.outcome.shot_type,
        },
        "rally_length": e.rally_length,
        "rally_category": e.rally_category,
        "streak_continuing": e.streak_continuing,
        "streak_broken": e.streak_broken,
        "comeback_threshold": e.comeback_threshold,
        "deciding_set_point": e.deciding_set_point,
    }


def save_replay(
    events: list[PointEvent],
    config: MatchConfig,
    profile_versions: dict[str, str],
    directory: str | Path,
) -> Path:
    """Save full event log + metadata for replay."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    meta = ReplayMetadata(
        match_id=config.match_id,
        seed=config.seed,
        config={
            "match_id": config.match_id,
            "player_a_id": config.player_a_id,
            "player_b_id": config.player_b_id,
            "seed": config.seed,
            "best_of": config.best_of,
            "games_to_win_set": config.games_to_win_set,
            "win_by": config.win_by,
        },
        profile_versions=profile_versions,
        event_count=len(events),
    )
    meta_path = path / f"{config.match_id}_meta.json"
    events_path = path / f"{config.match_id}_events.json"
    meta_path.write_text(json.dumps(asdict(meta), indent=2))
    events_path.write_text(json.dumps([event_to_dict(e) for e in events], indent=2))
    return path


def load_events(match_id: str, directory: str | Path) -> tuple[ReplayMetadata, list[dict]]:
    """Load metadata and event list (as dicts) for a match."""
    path = Path(directory)
    meta_path = path / f"{match_id}_meta.json"
    events_path = path / f"{match_id}_events.json"
    meta = ReplayMetadata(**json.loads(meta_path.read_text()))
    events = json.loads(events_path.read_text())
    return meta, events


@dataclass
class MatchSummary:
    """Aggregated per-match summary for backtesting."""
    match_id: str
    winner_id: str
    sets_score: tuple[int, int]
    total_points: int
    total_rallies: int
    avg_rally_length: float


def summarize_match(events: list[PointEvent], winner_id: str) -> MatchSummary:
    """Build MatchSummary from event list."""
    if not events:
        return MatchSummary(
            match_id="",
            winner_id=winner_id,
            sets_score=(0, 0),
            total_points=0,
            total_rallies=0,
            avg_rally_length=0.0,
        )
    e_last = events[-1]
    total_rallies = sum(e.rally_length for e in events)
    return MatchSummary(
        match_id=e_last.match_id,
        winner_id=winner_id,
        sets_score=e_last.set_scores_after[:2] if len(e_last.set_scores_after) >= 2 else (0, 0),
        total_points=len(events),
        total_rallies=total_rallies,
        avg_rally_length=total_rallies / len(events),
    )
