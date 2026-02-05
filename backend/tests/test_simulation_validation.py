"""
Validation test for the simulation engine: run thousands of random games,
aggregate statistics, and compare to real-life table tennis benchmarks.

Real-life benchmarks (sources in BENCHMARK_SOURCES):
- Rally length distribution: 56% short (1-3 shots), 34% medium (4-7), 10% long (8+)
  Source: Samson Dubina / Newgy, professional tournament rally statistics.
- Average points per game: ~18-22 typical for 11-point win-by-2 games (no exact public aggregate).
- Set score distribution and win %: reported for comparison; no strict public benchmarks.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pytest

# Run from project root: python -m pytest backend/tests/test_simulation_validation.py -v
_root = Path(__file__).resolve().parent.parent.parent
_backend = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from backend.simulation.schemas import MatchConfig
from backend.simulation.orchestrator import MatchOrchestrator, sets_to_win_match
from backend.simulation.profiles import ProfileStore, default_profile


# ---------- Real-life benchmarks (internet / research) ----------
# [1] Samson Dubina / Newgy: "Table Tennis Rally Statistics" – professional tournament.
#     12% 1st ball, 18% 2nd, 26% 3rd → 56% ≤3 shots (short); 13+11+6+4% = 34% for 4-7 (medium); 10% 8+ (long).
BENCHMARK_SOURCES = {
    "rally_dist": "Samson Dubina / Newgy, professional table tennis rally statistics",
}
# Target: short (1-3) 56%, medium (4-7) 34%, long (8+) 10%
REAL_LIFE_RALLY_SHORT_PCT = 0.56
REAL_LIFE_RALLY_MEDIUM_PCT = 0.34
REAL_LIFE_RALLY_LONG_PCT = 0.10
# Tolerance for assertion (stochastic): ±5% per category
RALLY_DIST_TOLERANCE = 0.05
# Typical 11-point win-by-2 games: average total points per game usually in this range
EXPECTED_AVG_POINTS_PER_GAME_MIN = 16
EXPECTED_AVG_POINTS_PER_GAME_MAX = 26

# Number of matches for validation (can override with env SIM_VALIDATION_MATCHES).
# Use 2000+ for CI; use 5000-10000 for tighter confidence: SIM_VALIDATION_MATCHES=5000 pytest ...
DEFAULT_VALIDATION_MATCHES = int(os.environ.get("SIM_VALIDATION_MATCHES", "2000"))


@dataclass
class AggregatedStats:
    """Aggregate statistics from many simulated matches."""
    total_matches: int = 0
    total_points: int = 0
    total_games: int = 0  # count of completed sets × (games in that set)
    rally_lengths: list[int] = field(default_factory=list)
    set_scores: list[tuple[int, int]] = field(default_factory=list)  # (sets_a, sets_b) per match
    higher_ranked_wins: int = 0  # when we designate A as higher ranked
    matches_with_higher_ranked: int = 0

    @property
    def avg_points_per_game(self) -> float:
        if self.total_games <= 0:
            return 0.0
        return self.total_points / self.total_games

    def rally_distribution(self) -> tuple[float, float, float]:
        """Returns (short_pct, medium_pct, long_pct) for rallies 1-3, 4-7, 8+."""
        if not self.rally_lengths:
            return 0.0, 0.0, 0.0
        short = sum(1 for r in self.rally_lengths if r <= 3)
        medium = sum(1 for r in self.rally_lengths if 4 <= r <= 7)
        long_ = sum(1 for r in self.rally_lengths if r >= 8)
        n = len(self.rally_lengths)
        return short / n, medium / n, long_ / n

    def set_score_distribution(self) -> dict[tuple[int, int], float]:
        """Returns proportion of matches ending at each set score (e.g. (3,0), (3,1), (2,3))."""
        if not self.set_scores:
            return {}
        counts: dict[tuple[int, int], int] = defaultdict(int)
        for s in self.set_scores:
            counts[s] += 1
        n = len(self.set_scores)
        return {k: v / n for k, v in counts.items()}

    def higher_ranked_win_pct(self) -> float:
        if self.matches_with_higher_ranked <= 0:
            return 0.0
        return self.higher_ranked_wins / self.matches_with_higher_ranked


def run_matches_and_aggregate(
    n_matches: int,
    player_a_elo: float = 0.0,
    player_b_elo: float = 0.0,
    best_of: int = 5,
    base_seed: int = 42,
) -> AggregatedStats:
    """
    Run n_matches with given profile strengths (elo_advantage for baseline_point_win).
    A is "higher ranked" when player_a_elo > player_b_elo.
    """
    store = ProfileStore()
    store.put(default_profile("a", elo_advantage=player_a_elo))
    store.put(default_profile("b", elo_advantage=player_b_elo))
    config = MatchConfig(
        match_id="val",
        player_a_id="a",
        player_b_id="b",
        seed=base_seed,
        best_of=best_of,
    )
    sets_needed = sets_to_win_match(best_of)
    agg = AggregatedStats()
    higher_ranked_is_a = player_a_elo > player_b_elo

    for i in range(n_matches):
        config = MatchConfig(
            match_id=f"val-{i}",
            player_a_id="a",
            player_b_id="b",
            seed=base_seed + i,
            best_of=best_of,
        )
        orch = MatchOrchestrator(config, store)
        events = list(orch.run())
        if not events:
            continue
        agg.total_matches += 1
        last = events[-1]
        set_scores = last.set_scores_after
        agg.set_scores.append((set_scores[0], set_scores[1]))
        winner_a = set_scores[0] >= sets_needed
        if higher_ranked_is_a and winner_a:
            agg.higher_ranked_wins += 1
        elif not higher_ranked_is_a and not winner_a:
            agg.higher_ranked_wins += 1
        agg.matches_with_higher_ranked += 1

        # Points per set (each set's total points = games in that set)
        points_this_match = 0
        games_this_match = 0
        current_set = -1
        points_in_set = 0
        for ev in events:
            agg.rally_lengths.append(ev.rally_length)
            if ev.set_index != current_set:
                if current_set >= 0:
                    games_this_match += 1
                    points_this_match += points_in_set
                current_set = ev.set_index
                points_in_set = 0
            points_in_set += 1
        if current_set >= 0:
            games_this_match += 1
            points_this_match += points_in_set
        agg.total_points += points_this_match
        agg.total_games += games_this_match

    return agg


class TestSimulationValidation:
    """Run many matches and compare aggregate stats to real-life benchmarks."""

    @pytest.fixture(scope="class")
    def agg_equal(self):
        """Aggregate from matches with equal strength (0.5 vs 0.5)."""
        return run_matches_and_aggregate(
            DEFAULT_VALIDATION_MATCHES,
            player_a_elo=0.0,
            player_b_elo=0.0,
            best_of=5,
            base_seed=12345,
        )

    @pytest.fixture(scope="class")
    def agg_unequal(self):
        """Aggregate from matches with favorite (0.05 vs -0.05 ≈ 55% vs 45% point win)."""
        return run_matches_and_aggregate(
            DEFAULT_VALIDATION_MATCHES,
            player_a_elo=0.05,
            player_b_elo=-0.05,
            best_of=5,
            base_seed=54321,
        )

    def test_rally_distribution_matches_real_life(self, agg_equal):
        """
        Rally length distribution (short/medium/long) should match real-life
        benchmarks from professional table tennis (Newgy / Samson Dubina).
        """
        short, medium, long_ = agg_equal.rally_distribution()
        assert REAL_LIFE_RALLY_SHORT_PCT - RALLY_DIST_TOLERANCE <= short <= REAL_LIFE_RALLY_SHORT_PCT + RALLY_DIST_TOLERANCE, (
            f"Rally short % {short:.3f} outside benchmark {REAL_LIFE_RALLY_SHORT_PCT} ± {RALLY_DIST_TOLERANCE}"
        )
        assert REAL_LIFE_RALLY_MEDIUM_PCT - RALLY_DIST_TOLERANCE <= medium <= REAL_LIFE_RALLY_MEDIUM_PCT + RALLY_DIST_TOLERANCE, (
            f"Rally medium % {medium:.3f} outside benchmark {REAL_LIFE_RALLY_MEDIUM_PCT} ± {RALLY_DIST_TOLERANCE}"
        )
        assert REAL_LIFE_RALLY_LONG_PCT - RALLY_DIST_TOLERANCE <= long_ <= REAL_LIFE_RALLY_LONG_PCT + RALLY_DIST_TOLERANCE, (
            f"Rally long % {long_:.3f} outside benchmark {REAL_LIFE_RALLY_LONG_PCT} ± {RALLY_DIST_TOLERANCE}"
        )

    def test_average_points_per_game_in_reasonable_range(self, agg_equal):
        """Average points per game (11-point win-by-2) should be in typical range ~16-26."""
        avg = agg_equal.avg_points_per_game
        assert EXPECTED_AVG_POINTS_PER_GAME_MIN <= avg <= EXPECTED_AVG_POINTS_PER_GAME_MAX, (
            f"Avg points per game {avg:.1f} outside expected range [{EXPECTED_AVG_POINTS_PER_GAME_MIN}, {EXPECTED_AVG_POINTS_PER_GAME_MAX}]"
        )

    def test_higher_ranked_win_percentage_above_fifty(self, agg_unequal):
        """When one player has higher strength, they should win more than 50% of matches."""
        pct = agg_unequal.higher_ranked_win_pct()
        assert pct >= 0.52, (
            f"Higher-ranked win % {pct:.2%} should be >= 52%"
        )

    def test_set_score_distribution_reported(self, agg_equal):
        """Set score distribution (3-0, 3-1, 3-2, etc.) is reported for sanity."""
        dist = agg_equal.set_score_distribution()
        assert len(dist) >= 1
        # Best-of-5: possible outcomes (3,0), (3,1), (3,2), (0,3), (1,3), (2,3)
        for (sa, sb), pct in dist.items():
            assert 0 <= pct <= 1
            assert sa == 3 or sb == 3

    def test_validation_report(self, agg_equal, agg_unequal):
        """Print a short report of simulated vs benchmark stats (for manual check)."""
        short, medium, long_ = agg_equal.rally_distribution()
        set_dist = agg_equal.set_score_distribution()
        print("\n--- Simulation validation report ---")
        print(f"  Matches (equal): {agg_equal.total_matches}, points: {agg_equal.total_points}, games: {agg_equal.total_games}")
        print(f"  Rally distribution: short={short:.2%}, medium={medium:.2%}, long={long_:.2%}")
        print(f"  Benchmark: short={REAL_LIFE_RALLY_SHORT_PCT:.0%}, medium={REAL_LIFE_RALLY_MEDIUM_PCT:.0%}, long={REAL_LIFE_RALLY_LONG_PCT:.0%} (source: {BENCHMARK_SOURCES['rally_dist']})")
        print(f"  Avg points per game: {agg_equal.avg_points_per_game:.2f}")
        print(f"  Set score distribution: {dict((k, f'{v:.1%}') for k, v in sorted(set_dist.items()))}")
        print(f"  Higher-ranked win % (unequal): {agg_unequal.higher_ranked_win_pct():.1%}")
        print("------------------------------------")
