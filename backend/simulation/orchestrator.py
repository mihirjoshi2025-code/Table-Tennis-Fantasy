"""
Match Orchestrator: set progression (to 11, win by 2; deciding set), set context.
Applies adjustments between sets (momentum carryover, fatigue recovery).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterator

from .schemas import (
    PointEvent,
    PointEventOutcome,
    MatchConfig,
    MatchSnapshot,
)
from .point_simulator import PointSimulator
from .state_tracker import SetState, MomentumState
from .fatigue_model import FatigueModel, FatigueState
from .profiles import PlayerProfile, ProfileStore
from .probability_engine import ProbabilityEngine, MatchContext
from .rng import SeededRNG


def set_won(games_a: int, games_b: int, to_win: int = 11, win_by: int = 2) -> str | None:
    """Returns 'a' or 'b' if someone won the set, else None."""
    if games_a >= to_win and games_a - games_b >= win_by:
        return "a"
    if games_b >= to_win and games_b - games_a >= win_by:
        return "b"
    return None


def sets_to_win_match(best_of: int) -> int:
    return (best_of // 2) + 1


@dataclass
class OrchestratorState:
    set_index: int
    game_index: int
    set_state: SetState
    set_scores: list[int]  # [sets won by A, sets won by B]
    server_id: str
    point_index: int
    momentum: MomentumState
    fatigue_a: FatigueState
    fatigue_b: FatigueState
    points_in_current_set: int
    completed: bool
    winner_id: str | None = None


class MatchOrchestrator:
    """
    Runs a full match point-by-point. Yields PointEvents (or emits via callback).
    Uses PointSimulator, FatigueModel, and set rules.
    """

    def __init__(
        self,
        config: MatchConfig,
        profile_store: ProfileStore,
        prob_engine: ProbabilityEngine | None = None,
        fatigue_model: FatigueModel | None = None,
    ) -> None:
        self.config = config
        self.profile_store = profile_store
        self.prob_engine = prob_engine or ProbabilityEngine()
        self.fatigue_model = fatigue_model or FatigueModel()
        self.rng = SeededRNG(config.seed)
        self.point_sim = PointSimulator(self.prob_engine, self.rng)
        self._pa = profile_store.get(config.player_a_id)
        self._pb = profile_store.get(config.player_b_id)
        if not self._pa or not self._pb:
            raise ValueError("Both players must have profiles in the store")

    def _server_id(self, state: OrchestratorState) -> str:
        # Alternate serve every 2 points (simplified)
        total_points_in_set = state.set_state.games_a + state.set_state.games_b
        if (total_points_in_set // 2) % 2 == 0:
            return self.config.player_a_id
        return self.config.player_b_id

    def run(
        self,
        on_point: Callable[[PointEvent], None] | None = None,
        max_points: int | None = None,
    ) -> Iterator[PointEvent]:
        """
        Run match to completion (or until max_points). Yields PointEvent per point.
        Optionally call on_point(event) for each event.
        """
        state = OrchestratorState(
            set_index=0,
            game_index=0,
            set_state=SetState(0, 0, 0),
            set_scores=[0, 0],
            server_id=self.config.player_a_id,
            point_index=0,
            momentum=MomentumState(),
            fatigue_a=FatigueState(),
            fatigue_b=FatigueState(),
            points_in_current_set=0,
            completed=False,
            winner_id=None,
        )
        best_of = self.config.best_of
        to_win_set = self.config.games_to_win_set
        win_by = self.config.win_by
        sets_needed = sets_to_win_match(best_of)
        events_list: list[PointEvent] = []

        while not state.completed:
            if max_points is not None and state.point_index >= max_points:
                break

            ctx = MatchContext(
                server_id=state.server_id,
                games_a=state.set_state.games_a,
                games_b=state.set_state.games_b,
                set_index=state.set_index,
                best_of=best_of,
                momentum=state.momentum,
                fatigue_a=state.fatigue_a.level,
                fatigue_b=state.fatigue_b.level,
                points_in_set=state.points_in_current_set,
                to_win=to_win_set,
                win_by=win_by,
            )
            outcome, rally_length, probs = self.point_sim.sample_point(
                self._pa,
                self._pb,
                ctx,
                self.config.player_a_id,
                self.config.player_b_id,
            )
            # Capture streak state before updating (for streak_broken tag)
            was_b_on_streak_3_plus = state.momentum.streak_b >= 3
            was_a_on_streak_3_plus = state.momentum.streak_a >= 3

            score_before = (state.set_state.games_a, state.set_state.games_b)
            if outcome.winner_id == self.config.player_a_id:
                state.set_state.games_a += 1
                state.momentum.record_point(True)
            else:
                state.set_state.games_b += 1
                state.momentum.record_point(False)
            state.set_state.points_played += 1
            state.points_in_current_set += 1
            state.point_index += 1

            # Fatigue update
            self.fatigue_model.update_after_point(
                state.fatigue_a,
                state.fatigue_b,
                rally_length,
                state.set_state.games_a,
                state.set_state.games_b,
                self._pa.fatigue_sensitivity,
                self._pb.fatigue_sensitivity,
            )

            score_after = (state.set_state.games_a, state.set_state.games_b)
            set_scores_before = tuple(state.set_scores)
            streak_continuing = None
            if state.momentum.streak_a >= 2 and outcome.winner_id == self.config.player_a_id:
                streak_continuing = self.config.player_a_id
            elif state.momentum.streak_b >= 2 and outcome.winner_id == self.config.player_b_id:
                streak_continuing = self.config.player_b_id
            streak_broken = (outcome.winner_id == self.config.player_a_id and was_b_on_streak_3_plus) or (
                outcome.winner_id == self.config.player_b_id and was_a_on_streak_3_plus
            )
            deciding = state.set_index == best_of - 1 and max(state.set_scores) == sets_needed - 1
            comeback = False  # optional: detect comeback threshold

            # Check set winner and update set scores for event
            winner = set_won(state.set_state.games_a, state.set_state.games_b, to_win_set, win_by)
            set_scores_after_list = list(state.set_scores)
            if winner == "a":
                set_scores_after_list[0] += 1
            elif winner == "b":
                set_scores_after_list[1] += 1
            set_scores_after = tuple(set_scores_after_list)

            event = PointEvent(
                match_id=self.config.match_id,
                point_index=state.point_index,
                set_index=state.set_index,
                game_index=state.set_state.games_a + state.set_state.games_b - 1,
                score_before=score_before,
                score_after=score_after,
                set_scores_before=set_scores_before,
                set_scores_after=set_scores_after,
                server_id=state.server_id,
                outcome=PointEventOutcome(
                    winner_id=outcome.winner_id,
                    loser_id=outcome.loser_id,
                    shot_type=outcome.shot_type.value,
                ),
                rally_length=rally_length,
                rally_category=outcome.rally_category.value,
                streak_continuing=streak_continuing,
                streak_broken=streak_broken,
                comeback_threshold=comeback,
                deciding_set_point=deciding,
                probabilities_snapshot={"p_a_wins": probs.p_a_wins, "p_b_wins": probs.p_b_wins} if probs else None,
            )
            events_list.append(event)
            state.set_scores = list(set_scores_after_list)

            # Alternate server every 2 points within set
            points_in_set = state.set_state.games_a + state.set_state.games_b
            if points_in_set >= 2 and points_in_set % 2 == 0:
                state.server_id = (
                    self.config.player_b_id
                    if state.server_id == self.config.player_a_id
                    else self.config.player_a_id
                )

            if on_point:
                on_point(event)
            yield event

            if winner is not None:
                self.fatigue_model.recover_between_sets(state.fatigue_a, state.fatigue_b)
                if state.set_scores[0] >= sets_needed or state.set_scores[1] >= sets_needed:
                    state.completed = True
                    state.winner_id = self.config.player_a_id if state.set_scores[0] >= sets_needed else self.config.player_b_id
                    break
                # Next set
                state.set_index += 1
                state.set_state = SetState(0, 0, 0)
                state.points_in_current_set = 0
                state.server_id = self.config.player_b_id if state.server_id == self.config.player_a_id else self.config.player_a_id
