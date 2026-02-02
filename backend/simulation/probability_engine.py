"""
Probability Engine: computes outcome probabilities per point.
Inputs: player profiles, match context (score, set, streaks, fatigue, deciding set).
Output: probability vector for A wins (by shot type), B wins (by shot type), rally length.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .schemas import ShotType, RallyLengthCategory
from .state_tracker import MomentumState, is_pressure_zone, is_deciding_set
from .fatigue_model import FatigueModel

if TYPE_CHECKING:
    from .profiles import PlayerProfile


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class MatchContext:
    """Current match state for probability computation."""
    server_id: str
    games_a: int
    games_b: int
    set_index: int
    best_of: int
    momentum: MomentumState
    fatigue_a: float
    fatigue_b: float
    points_in_set: int
    to_win: int = 11
    win_by: int = 2


@dataclass
class OutcomeProbs:
    """Structured probabilities for diagnostics and sampling."""
    p_a_wins: float
    p_b_wins: float
    # Conditional shot type given winner (A or B)
    p_shot_a: tuple[float, float, float]  # forehand, backhand, service
    p_shot_b: tuple[float, float, float]
    # Rally length category weights (short, medium, long)
    rally_weights: tuple[float, float, float]


class ProbabilityEngine:
    """
    Composables: serve effect, clutch, momentum, fatigue.
    Returns OutcomeProbs and supports sampling.
    """

    def __init__(
        self,
        momentum_alpha: float = 0.15,
        fatigue_beta: float = 0.15,
        clutch_scale: float = 1.0,
    ) -> None:
        self.momentum_alpha = momentum_alpha
        self.fatigue_beta = fatigue_beta
        self.clutch_scale = clutch_scale

    def compute(
        self,
        profile_a: PlayerProfile,
        profile_b: PlayerProfile,
        ctx: MatchContext,
        player_a_id: str,
        player_b_id: str,
    ) -> OutcomeProbs:
        """
        Compute full outcome probability vector.
        """
        p_base = profile_a.baseline_point_win
        # Serve multiplier: if A is serving, boost A's win prob
        if ctx.server_id == player_a_id:
            p_base *= profile_a.serve_multiplier
        else:
            p_base *= (1.0 / profile_b.serve_multiplier)
        # Clamp to (0, 1) then renormalize vs B
        p_base = max(0.15, min(0.85, p_base))

        # Clutch: pressure zone or deciding set
        pressure = is_pressure_zone(ctx.games_a, ctx.games_b, ctx.to_win, ctx.win_by)
        deciding = is_deciding_set(ctx.set_index, ctx.best_of)
        if pressure or deciding:
            p_base += profile_a.clutch_modifier * self.clutch_scale
            p_base = max(0.15, min(0.85, p_base))

        # Momentum
        mom_a = ctx.momentum.momentum_score_a()
        p_base += self.momentum_alpha * mom_a
        p_base = max(0.15, min(0.85, p_base))

        # Fatigue penalty (both players; net effect on A)
        pen_a = FatigueModel.fatigue_penalty(ctx.fatigue_a, self.fatigue_beta)
        pen_b = FatigueModel.fatigue_penalty(ctx.fatigue_b, self.fatigue_beta)
        # A's effective win prob scales down if A more tired, up if B more tired
        p_base = p_base * (pen_a / pen_b)
        p_base = max(0.15, min(0.85, p_base))

        # Streak bias: small boost if A on streak
        if ctx.momentum.streak_a >= 3:
            p_base += profile_a.streak_bias
        if ctx.momentum.streak_b >= 3:
            p_base -= profile_b.streak_bias
        p_base = max(0.15, min(0.85, p_base))

        p_a_wins = p_base
        p_b_wins = 1.0 - p_a_wins

        # Shot type mix for A and B (forehand, backhand, service)
        sa, sb, sc = profile_a.style_mix
        p_shot_a = (sa, sb, sc)
        sa2, sb2, sc2 = profile_b.style_mix
        p_shot_b = (sa2, sb2, sc2)

        # Rally length: blend both profiles
        ra = profile_a.rally_length_dist
        rb = profile_b.rally_length_dist
        rally_weights = (
            (ra[0] + rb[0]) / 2,
            (ra[1] + rb[1]) / 2,
            (ra[2] + rb[2]) / 2,
        )
        total_r = sum(rally_weights)
        rally_weights = tuple(w / total_r for w in rally_weights)

        return OutcomeProbs(
            p_a_wins=p_a_wins,
            p_b_wins=p_b_wins,
            p_shot_a=p_shot_a,
            p_shot_b=p_shot_b,
            rally_weights=rally_weights,
        )