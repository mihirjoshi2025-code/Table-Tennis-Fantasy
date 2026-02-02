"""
Momentum & State Tracker: set-level and match-level state.
Tracks consecutive points, deficits, last N events, derives momentum score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque


@dataclass
class SetState:
    """Score and point count within one set."""
    games_a: int = 0
    games_b: int = 0
    points_played: int = 0

    def score(self) -> tuple[int, int]:
        return (self.games_a, self.games_b)


@dataclass
class MomentumState:
    """
    Rolling window of recent outcomes and streak info.
    momentum_score is a continuous value per player (e.g. -1..1).
    """
    window_size: int = 12
    # Last N point outcomes: 1 = A won, -1 = B won
    last_outcomes: deque[int] = field(default_factory=lambda: deque(maxlen=12))
    streak_a: int = 0
    streak_b: int = 0
    max_deficit_a: int = 0
    max_deficit_b: int = 0

    def record_point(self, winner_is_a: bool) -> None:
        outcome = 1 if winner_is_a else -1
        self.last_outcomes.append(outcome)
        if winner_is_a:
            self.streak_a += 1
            self.streak_b = 0
        else:
            self.streak_b += 1
            self.streak_a = 0

    def momentum_score_a(self, streak_boost: float = 0.08) -> float:
        """
        Weighted sum of recent outcomes; small boost for current streak.
        Result in roughly [-1, 1].
        """
        if not self.last_outcomes:
            return 0.0
        n = len(self.last_outcomes)
        total = 0.0
        for i, o in enumerate(self.last_outcomes):
            # More recent = higher weight
            w = (i + 1) / n
            total += w * (1.0 if o == 1 else -1.0)
        # Normalize to [-1, 1]
        total /= sum((i + 1) / n for i in range(n))
        if self.streak_a >= 3:
            total = min(1.0, total + streak_boost * min(self.streak_a, 5))
        if self.streak_b >= 3:
            total = max(-1.0, total - streak_boost * min(self.streak_b, 5))
        return max(-1.0, min(1.0, total))

    def momentum_score_b(self, streak_boost: float = 0.08) -> float:
        return -self.momentum_score_a(streak_boost=streak_boost)

    def streak_broken_after_3plus(self, winner_is_a: bool) -> bool:
        """True if the other player just ended a 3+ streak."""
        if winner_is_a and self.streak_b >= 3:
            return True  # B was on streak, A won
        if not winner_is_a and self.streak_a >= 3:
            return True
        return False

    def is_streak_continuing(self, winner_is_a: bool) -> bool:
        """True if winner extended their streak (had at least 1 before)."""
        if winner_is_a and self.streak_a >= 2:  # was 1+, now 2+
            return True
        if not winner_is_a and self.streak_b >= 2:
            return True
        return False


def is_pressure_zone(games_a: int, games_b: int, to_win: int = 11, win_by: int = 2) -> bool:
    """Deciding moment: near end of set (e.g. 9-9, 10-10)."""
    return (
        max(games_a, games_b) >= to_win - 2
        and abs(games_a - games_b) <= win_by
    )


def is_deciding_set(set_index: int, best_of: int) -> bool:
    """True if this set is the final possible set (e.g. set 2 in best of 3)."""
    return set_index == best_of - 1
