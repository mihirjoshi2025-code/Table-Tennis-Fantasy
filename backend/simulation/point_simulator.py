"""
Point Simulator: uses Probability Engine + seeded RNG to sample point outcome.
Emits rich PointEvent; updates internal state (rally length, streaks).
"""
from __future__ import annotations

from .schemas import (
    PointEvent,
    PointEventOutcome,
    ShotType,
    RallyLengthCategory,
    rally_category_from_length,
    PointOutcome,
)
from .probability_engine import ProbabilityEngine, MatchContext, OutcomeProbs
from .state_tracker import MomentumState, SetState, is_pressure_zone, is_deciding_set
from .rng import SeededRNG
from .profiles import PlayerProfile

# Rally length bounds per category (for sampling)
RALLY_LENGTH_BY_CATEGORY = {
    RallyLengthCategory.SHORT: (1, 3),
    RallyLengthCategory.MEDIUM: (4, 7),
    RallyLengthCategory.LONG: (8, 15),
}


def sample_shot_type(rng: SeededRNG, weights: tuple[float, float, float]) -> ShotType:
    """Sample forehand / backhand / service from weights."""
    choices = [ShotType.FOREHAND, ShotType.BACKHAND, ShotType.SERVICE]
    w = list(weights)
    total = sum(w)
    if total <= 0:
        return rng.choice(choices)
    return rng.choices(choices, weights=w, k=1)[0]


def sample_rally_length(rng: SeededRNG, category: RallyLengthCategory) -> int:
    lo, hi = RALLY_LENGTH_BY_CATEGORY[category]
    return rng.randint(lo, hi)


def sample_rally_category(rng: SeededRNG, weights: tuple[float, float, float]) -> RallyLengthCategory:
    cats = [RallyLengthCategory.SHORT, RallyLengthCategory.MEDIUM, RallyLengthCategory.LONG]
    total = sum(weights)
    if total <= 0:
        return rng.choice(cats)
    return rng.choices(cats, weights=weights, k=1)[0]


class PointSimulator:
    """
    Samples one point given context; returns PointOutcome and rally length.
    Caller (orchestrator) builds PointEvent and updates momentum/fatigue.
    """

    def __init__(self, prob_engine: ProbabilityEngine, rng: SeededRNG) -> None:
        self.prob_engine = prob_engine
        self.rng = rng

    def sample_point(
        self,
        profile_a: PlayerProfile,
        profile_b: PlayerProfile,
        ctx: MatchContext,
        player_a_id: str,
        player_b_id: str,
    ) -> tuple[PointOutcome, int, OutcomeProbs]:
        """
        Returns (outcome, rally_length, probs_for_diagnostics).
        """
        probs = self.prob_engine.compute(profile_a, profile_b, ctx, player_a_id, player_b_id)
        a_wins = self.rng.random() < probs.p_a_wins
        rally_cat = sample_rally_category(self.rng, probs.rally_weights)
        rally_length = sample_rally_length(self.rng, rally_cat)
        if a_wins:
            shot = sample_shot_type(self.rng, probs.p_shot_a)
            outcome = PointOutcome(
                winner_id=player_a_id,
                loser_id=player_b_id,
                shot_type=shot,
                rally_length=rally_length,
                rally_category=rally_cat,
            )
        else:
            shot = sample_shot_type(self.rng, probs.p_shot_b)
            outcome = PointOutcome(
                winner_id=player_b_id,
                loser_id=player_a_id,
                shot_type=shot,
                rally_length=rally_length,
                rally_category=rally_cat,
            )
        return outcome, rally_length, probs
