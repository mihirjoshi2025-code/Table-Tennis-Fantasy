"""
Event output schema and shared types for the AI Match Simulation Engine.
Rich point events and match snapshots for WebSocket feeds and replay.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ShotType(str, Enum):
    """How the point was won (or lost)."""
    FOREHAND = "forehand"
    BACKHAND = "backhand"
    SERVICE = "service"
    UNFORCED_ERROR = "unforced_error"


class RallyLengthCategory(str, Enum):
    """Rally length bucket for analytics."""
    SHORT = "short"      # 1-3 shots
    MEDIUM = "medium"    # 4-7
    LONG = "long"        # 8+


@dataclass(frozen=True)
class PointOutcome:
    """Who won and how (shot type)."""
    winner_id: str
    loser_id: str
    shot_type: ShotType
    rally_length: int
    rally_category: RallyLengthCategory


def rally_category_from_length(length: int) -> RallyLengthCategory:
    if length <= 3:
        return RallyLengthCategory.SHORT
    if length <= 7:
        return RallyLengthCategory.MEDIUM
    return RallyLengthCategory.LONG


@dataclass
class PointEvent:
    """
    Rich point event emitted after each simulated point.
    Suitable for WebSocket payloads and replay.
    """
    match_id: str
    point_index: int
    set_index: int
    game_index: int  # game within set (0-based)
    score_before: tuple[int, int]  # (player_a_games, player_b_games) in this set
    score_after: tuple[int, int]
    set_scores_before: tuple[int, ...]  # (sets won by A, sets won by B, ...)
    set_scores_after: tuple[int, ...]
    server_id: str
    outcome: PointEventOutcome
    rally_length: int
    rally_category: str
    # Optional context for narration / momentum
    streak_continuing: str | None = None  # id of player on streak
    streak_broken: bool = False
    comeback_threshold: bool = False
    deciding_set_point: bool = False
    # Diagnostics
    probabilities_snapshot: dict[str, Any] | None = None


@dataclass
class PointEventOutcome:
    """Who won and how, for PointEvent."""
    winner_id: str
    loser_id: str
    shot_type: str


@dataclass
class MatchSnapshot:
    """
    Partial-match snapshot at a point in time.
    For UI and realtime feeds.
    """
    match_id: str
    point_index: int
    set_index: int
    game_index: int
    set_scores: tuple[int, ...]
    current_game_score: tuple[int, int]
    server_id: str
    completed: bool
    winner_id: str | None = None
    events_count: int = 0


@dataclass
class MatchConfig:
    """Configuration for a single match simulation."""
    match_id: str
    player_a_id: str
    player_b_id: str
    seed: int
    best_of: int = 5  # 3 or 5 sets
    games_to_win_set: int = 11
    win_by: int = 2
    deciding_set_games: int | None = None  # if different, e.g. first to 7
    profile_version: str = "v1"
