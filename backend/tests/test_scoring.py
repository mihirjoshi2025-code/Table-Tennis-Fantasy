"""
Tests for fantasy scoring (TABLE TENNIS FANTASY SCORING RUBRIC).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring import (
    MatchResult,
    MatchStats,
    build_stats_for_player,
    compute_fantasy_score,
    aggregate_stats_from_events,
    MATCH_WIN_POINTS,
    MATCH_LOSS_POINTS,
    SWEEP_BONUS,
    FIVE_SET_PARTICIPATION,
    SET_WON_POINTS,
    SET_LOST_POINTS,
    NET_DIFF_BONUS_POINTS,
    NET_DIFF_PENALTY_POINTS,
    COMEBACK_SET_POINTS,
    DECIDING_SET_WIN_POINTS,
    STREAK_BREAK_POINTS,
    STREAK_3_PLUS_POINTS,
    FOREHAND_WINNER_POINTS,
    DEFEATS_HIGHER_RANKED_POINTS,
    HEAVY_FAVORITE_LOSS_POINTS,
)


class TestCoreMatchScoring:
    def test_match_win(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=3, sets_loser=1, best_of=5)
        stats = build_stats_for_player("A", result)
        score = compute_fantasy_score(stats)
        assert stats.is_winner
        assert score >= MATCH_WIN_POINTS
        assert MATCH_WIN_POINTS == 10

    def test_match_loss(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=3, sets_loser=0, best_of=5)
        stats = build_stats_for_player("B", result)
        score = compute_fantasy_score(stats)
        assert not stats.is_winner
        assert score <= 0  # loss + set penalties (e.g. -3 - 3 = -6)
        assert MATCH_LOSS_POINTS == -3

    def test_sweep_bonus_best_of_5(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=3, sets_loser=0, best_of=5)
        stats = build_stats_for_player("A", result)
        score = compute_fantasy_score(stats)
        assert score == MATCH_WIN_POINTS + SWEEP_BONUS + 3 * SET_WON_POINTS
        assert SWEEP_BONUS == 4

    def test_sweep_bonus_best_of_3(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=2, sets_loser=0, best_of=3)
        stats = build_stats_for_player("A", result)
        score = compute_fantasy_score(stats)
        assert score == MATCH_WIN_POINTS + SWEEP_BONUS + 2 * SET_WON_POINTS

    def test_no_sweep_when_set_lost(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=3, sets_loser=1, best_of=5)
        stats = build_stats_for_player("A", result)
        score = compute_fantasy_score(stats)
        assert score == MATCH_WIN_POINTS + 3 * SET_WON_POINTS + 1 * SET_LOST_POINTS  # no sweep bonus

    def test_five_set_participation(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=3, sets_loser=2, best_of=5)
        stats_winner = build_stats_for_player("A", result)
        stats_loser = build_stats_for_player("B", result)
        s1 = compute_fantasy_score(stats_winner)
        s2 = compute_fantasy_score(stats_loser)
        assert FIVE_SET_PARTICIPATION == 2
        assert s1 == MATCH_WIN_POINTS + 3 * SET_WON_POINTS + 2 * SET_LOST_POINTS + FIVE_SET_PARTICIPATION
        assert s2 == MATCH_LOSS_POINTS + 2 * SET_WON_POINTS + 3 * SET_LOST_POINTS + FIVE_SET_PARTICIPATION


class TestSetAndPointPerformance:
    def test_set_won_lost(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=2, sets_loser=1, best_of=3)
        stats_a = build_stats_for_player("A", result)
        stats_b = build_stats_for_player("B", result)
        assert compute_fantasy_score(stats_a) == MATCH_WIN_POINTS + 2 * SET_WON_POINTS + 1 * SET_LOST_POINTS
        assert compute_fantasy_score(stats_b) == MATCH_LOSS_POINTS + 1 * SET_WON_POINTS + 2 * SET_LOST_POINTS

    def test_net_point_differential_bonus(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=3, sets_loser=0, best_of=5)
        stats = build_stats_for_player("A", result, net_point_differential=12)
        score = compute_fantasy_score(stats)
        assert score == MATCH_WIN_POINTS + SWEEP_BONUS + 3 * SET_WON_POINTS + NET_DIFF_BONUS_POINTS

    def test_net_point_differential_penalty(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=3, sets_loser=2, best_of=5)
        stats = build_stats_for_player("B", result, net_point_differential=-11)
        score = compute_fantasy_score(stats)
        assert NET_DIFF_PENALTY_POINTS in (score - (MATCH_LOSS_POINTS + 2 * SET_WON_POINTS + 3 * SET_LOST_POINTS + FIVE_SET_PARTICIPATION), score)


class TestClutchMomentum:
    def test_comeback_set(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=2, sets_loser=1, best_of=3)
        stats = build_stats_for_player("A", result, comeback_sets=1)
        score = compute_fantasy_score(stats)
        assert score == MATCH_WIN_POINTS + 2 * SET_WON_POINTS + 1 * SET_LOST_POINTS + COMEBACK_SET_POINTS

    def test_deciding_set_win(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=3, sets_loser=2, best_of=5)
        stats = build_stats_for_player("A", result, won_deciding_set=True)
        score = compute_fantasy_score(stats)
        assert DECIDING_SET_WIN_POINTS == 3
        assert score >= MATCH_WIN_POINTS + 3 * SET_WON_POINTS + 2 * SET_LOST_POINTS + FIVE_SET_PARTICIPATION + DECIDING_SET_WIN_POINTS

    def test_streak_break_and_streaks(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=2, sets_loser=0, best_of=3)
        stats = build_stats_for_player("A", result, streak_breaks=2, streaks_3_plus=3)
        score = compute_fantasy_score(stats)
        assert 2 * STREAK_BREAK_POINTS + 3 * STREAK_3_PLUS_POINTS == 2 + 3
        assert score == MATCH_WIN_POINTS + SWEEP_BONUS + 2 * SET_WON_POINTS + 2 + 3


class TestStyleBased:
    def test_forehand_backhand_service_winners(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=2, sets_loser=0, best_of=3)
        stats = build_stats_for_player(
            "A", result,
            forehand_winners=4,
            backhand_winners=2,
            service_winners=2,
        )
        score = compute_fantasy_score(stats)
        style_pts = 4 * FOREHAND_WINNER_POINTS + 2 * 0.5 + 2 * 0.5
        assert style_pts == 4.0
        assert score == MATCH_WIN_POINTS + SWEEP_BONUS + 2 * SET_WON_POINTS + style_pts

    def test_unforced_errors_penalty(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=2, sets_loser=0, best_of=3)
        stats = build_stats_for_player("A", result, unforced_errors=4)
        score = compute_fantasy_score(stats)
        assert score == MATCH_WIN_POINTS + SWEEP_BONUS + 2 * SET_WON_POINTS - 4 * 0.5


class TestRiskModifiers:
    def test_defeats_higher_ranked(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=2, sets_loser=1, best_of=3)
        stats = build_stats_for_player("A", result, defeated_higher_ranked=True)
        score = compute_fantasy_score(stats)
        assert score == MATCH_WIN_POINTS + 2 * SET_WON_POINTS + 1 * SET_LOST_POINTS + DEFEATS_HIGHER_RANKED_POINTS

    def test_heavy_favorite_loss(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=2, sets_loser=0, best_of=3)
        stats = build_stats_for_player("B", result, lost_as_heavy_favorite=True)
        score = compute_fantasy_score(stats)
        assert HEAVY_FAVORITE_LOSS_POINTS == -2
        assert score == MATCH_LOSS_POINTS + 0 * SET_WON_POINTS + 2 * SET_LOST_POINTS + HEAVY_FAVORITE_LOSS_POINTS

    def test_first_match_after_absence(self):
        result = MatchResult(winner_id="A", loser_id="B", sets_winner=2, sets_loser=0, best_of=3)
        stats = build_stats_for_player("A", result, first_match_after_absence=True)
        score = compute_fantasy_score(stats)
        assert score == MATCH_WIN_POINTS + SWEEP_BONUS + 2 * SET_WON_POINTS + 1


class TestAggregateFromEvents:
    def test_empty_events(self):
        stats_a, stats_b = aggregate_stats_from_events(
            [], winner_id="A", player_a_id="A", player_b_id="B", best_of=5
        )
        assert stats_a.player_id == "A"
        assert stats_b.player_id == "B"
        assert stats_a.is_winner
        assert not stats_b.is_winner
        assert stats_a.sets_won == 0 and stats_a.sets_lost == 0

    def test_single_event_dict(self):
        events = [
            {
                "outcome": {"winner_id": "A", "loser_id": "B", "shot_type": "forehand"},
                "set_index": 0,
                "score_before": (0, 0),
                "score_after": (1, 0),
                "set_scores_before": (0, 0),
                "set_scores_after": (0, 0),
                "streak_broken": False,
                "streak_continuing": None,
            }
        ]
        stats_a, stats_b = aggregate_stats_from_events(
            events, winner_id="A", player_a_id="A", player_b_id="B", best_of=3
        )
        assert stats_a.forehand_winners == 1
        assert stats_b.forehand_winners == 0

    def test_style_counts_from_events(self):
        events = []
        for i in range(5):
            events.append({
                "outcome": {"winner_id": "A", "loser_id": "B", "shot_type": "forehand"},
                "set_index": 0,
                "score_before": (i, 0),
                "score_after": (i + 1, 0),
                "set_scores_before": (0, 0),
                "set_scores_after": (0, 0),
                "streak_broken": False,
                "streak_continuing": "A" if i >= 2 else None,
            })
        events.append({
            "outcome": {"winner_id": "A", "loser_id": "B", "shot_type": "backhand"},
            "set_index": 0,
            "score_before": (5, 0),
            "score_after": (6, 0),
            "set_scores_before": (0, 0),
            "set_scores_after": (0, 0),
            "streak_broken": False,
            "streak_continuing": "A",
        })
        # Set ends (e.g. 11-0) - one set
        for j in range(5):
            events.append({
                "outcome": {"winner_id": "B", "loser_id": "A", "shot_type": "service"},
                "set_index": 0,
                "score_before": (6, j),
                "score_after": (6, j + 1),
                "set_scores_before": (0, 0),
                "set_scores_after": (0, 0),
                "streak_broken": False,
                "streak_continuing": None,
            })
        # End set 0: 6-5 B (B wins set)
        events.append({
            "outcome": {"winner_id": "B", "loser_id": "A", "shot_type": "forehand"},
            "set_index": 0,
            "score_before": (6, 5),
            "score_after": (6, 6),
            "set_scores_before": (0, 0),
            "set_scores_after": (0, 0),
            "streak_broken": False,
            "streak_continuing": None,
        })
        events.append({
            "outcome": {"winner_id": "B", "loser_id": "A", "shot_type": "forehand"},
            "set_index": 0,
            "score_before": (6, 6),
            "score_after": (6, 7),
            "set_scores_before": (0, 0),
            "set_scores_after": (0, 1),
            "streak_broken": False,
            "streak_continuing": None,
        })
        stats_a, stats_b = aggregate_stats_from_events(
            events, winner_id="B", player_a_id="A", player_b_id="B", best_of=3
        )
        assert stats_a.forehand_winners == 5
        assert stats_a.backhand_winners == 1
        assert stats_b.forehand_winners >= 1
        score_a = compute_fantasy_score(stats_a)
        score_b = compute_fantasy_score(stats_b)
        assert isinstance(score_a, (int, float))
        assert isinstance(score_b, (int, float))
