"""
Fatigue Model: accumulates fatigue from rallies, point count, and sets.
Modifies error rates and serve effectiveness; configurable per profile.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FatigueState:
    """Per-player fatigue level in [0, 1]."""
    level: float = 0.0

    def clamp(self) -> None:
        self.level = max(0.0, min(1.0, self.level))


def f_rally(rally_length: int) -> float:
    """Contribution to fatigue from rally length (e.g. longer = more fatigue)."""
    if rally_length <= 3:
        return 0.002
    if rally_length <= 7:
        return 0.006
    return 0.012


def g_set(points_in_set: int) -> float:
    """Contribution from set duration (more points = more fatigue)."""
    return min(0.15, points_in_set * 0.001)


@dataclass
class FatigueModel:
    """
    Updates fatigue after each point; applies recovery between sets.
    Calibrate w_rally and w_set per profile (via fatigue_sensitivity).
    """

    def __init__(
        self,
        w_rally: float = 1.0,
        w_set: float = 0.5,
        recovery_between_sets: float = 0.25,
    ) -> None:
        self.w_rally = w_rally
        self.w_set = w_set
        self.recovery_between_sets = recovery_between_sets

    def update_after_point(
        self,
        fatigue_a: FatigueState,
        fatigue_b: FatigueState,
        rally_length: int,
        points_in_set_a: int,
        points_in_set_b: int,
        sensitivity_a: float,
        sensitivity_b: float,
    ) -> None:
        """Both players accumulate fatigue; sensitivity scales the effect."""
        delta = self.w_rally * f_rally(rally_length) + self.w_set * (
            g_set(points_in_set_a) + g_set(points_in_set_b)
        ) / 2
        fatigue_a.level += delta * sensitivity_a
        fatigue_b.level += delta * sensitivity_b
        fatigue_a.clamp()
        fatigue_b.clamp()

    def recover_between_sets(self, fatigue_a: FatigueState, fatigue_b: FatigueState) -> None:
        """Partial recovery between sets."""
        fatigue_a.level = max(0.0, fatigue_a.level - self.recovery_between_sets)
        fatigue_b.level = max(0.0, fatigue_b.level - self.recovery_between_sets)
        fatigue_a.clamp()
        fatigue_b.clamp()

    @staticmethod
    def fatigue_penalty(fatigue_level: float, beta: float = 0.15) -> float:
        """
        Multiplier for winner/effectiveness: 1 - fatigue_level * beta.
        Used by Probability Engine to reduce serve and winner rates when tired.
        """
        return max(0.7, 1.0 - fatigue_level * beta)
