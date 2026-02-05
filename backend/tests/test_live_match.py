"""
Test suite for the scoring-simulation match feature: rankings DB, profile building,
live match flow (simulation → scoring), and real-time score display.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

# Run from project root: python -m pytest backend/tests/test_live_match.py
import sys
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from backend.rankings_db import (
    init_db,
    get_player,
    list_players_by_gender,
    build_profile_from_row,
    build_profile_store_for_match,
    PlayerRow,
)
from backend.scoring import aggregate_stats_from_events, compute_fantasy_score
from backend.simulation.schemas import MatchConfig
from backend.simulation.orchestrator import MatchOrchestrator, sets_to_win_match


# ---- Fixtures: minimal rankings JSON and DB ----
@pytest.fixture
def sample_rankings_path(tmp_path):
    data = {
        "men_singles_rankings": [
            {"rank": 1, "name": "Player A", "country": "USA", "points": 3000},
            {"rank": 2, "name": "Player B", "country": "CHN", "points": 2500},
        ],
        "women_singles_rankings": [
            {"rank": 1, "name": "Player C", "country": "JPN", "points": 2800},
            {"rank": 2, "name": "Player D", "country": "KOR", "points": 2200},
        ],
    }
    p = tmp_path / "rankings.json"
    p.write_text(json.dumps(data))
    return p


@pytest.fixture
def db_with_rankings(sample_rankings_path, tmp_path):
    db_path = tmp_path / "rankings.db"
    init_db(db_path, sample_rankings_path)
    return db_path


# ---- Rankings DB ----
class TestRankingsDB:
    def test_init_db_creates_players_table(self, tmp_path):
        init_db(tmp_path / "test.db", rankings_path=None)
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='players'")
        assert cur.fetchone() is not None
        conn.close()

    def test_load_rankings_populates_players(self, db_with_rankings):
        conn = sqlite3.connect(str(db_with_rankings))
        men = list_players_by_gender(conn, "men")
        women = list_players_by_gender(conn, "women")
        conn.close()
        assert len(men) == 2
        assert len(women) == 2
        assert men[0].name == "Player A"
        assert men[0].points == 3000
        assert men[0].gender == "men"
        assert women[0].name == "Player C"

    def test_get_player(self, db_with_rankings):
        conn = sqlite3.connect(str(db_with_rankings))
        row = get_player(conn, "player_a")
        conn.close()
        assert row is not None
        assert row.name == "Player A"
        assert row.serve_multiplier >= 1.0
        assert row.rally_short_pct + row.rally_medium_pct + row.rally_long_pct > 0
        assert row.style_forehand + row.style_backhand + row.style_service > 0

    def test_same_gender_only(self, db_with_rankings):
        conn = sqlite3.connect(str(db_with_rankings))
        men = list_players_by_gender(conn, "men")
        women = list_players_by_gender(conn, "women")
        conn.close()
        assert all(p.gender == "men" for p in men)
        assert all(p.gender == "women" for p in women)


# ---- Profile building from DB ----
class TestProfileFromDB:
    def test_build_profile_from_row(self, db_with_rankings):
        conn = sqlite3.connect(str(db_with_rankings))
        row_a = get_player(conn, "player_a")
        row_b = get_player(conn, "player_b")
        conn.close()
        assert row_a and row_b
        profile_a = build_profile_from_row(row_a, row_b.points)
        profile_b = build_profile_from_row(row_b, row_a.points)
        assert profile_a.player_id == "player_a"
        assert profile_b.player_id == "player_b"
        # Stronger player (A) should have baseline > 0.5
        assert profile_a.baseline_point_win > 0.5
        assert profile_b.baseline_point_win < 0.5
        assert 0.3 <= profile_a.baseline_point_win <= 0.7
        assert 0.3 <= profile_b.baseline_point_win <= 0.7
        assert profile_a.serve_multiplier >= 1.0
        assert len(profile_a.rally_length_dist) == 3
        assert abs(sum(profile_a.style_mix) - 1.0) < 0.01

    def test_build_profile_store_for_match(self, db_with_rankings):
        conn = sqlite3.connect(str(db_with_rankings))
        store = build_profile_store_for_match(conn, "player_a", "player_b")
        conn.close()
        pa = store.get("player_a")
        pb = store.get("player_b")
        assert pa is not None and pb is not None
        assert 0.3 <= pa.baseline_point_win <= 0.7 and 0.3 <= pb.baseline_point_win <= 0.7

    def test_build_profile_store_raises_for_missing_player(self, db_with_rankings):
        conn = sqlite3.connect(str(db_with_rankings))
        with pytest.raises(ValueError, match="Both players must exist"):
            build_profile_store_for_match(conn, "nonexistent", "player_b")
        conn.close()


# ---- Simulation → Scoring integration ----
class TestSimulationScoringIntegration:
    def test_two_same_gender_play_full_match(self, db_with_rankings):
        conn = sqlite3.connect(str(db_with_rankings))
        store = build_profile_store_for_match(conn, "player_a", "player_b")
        conn.close()
        config = MatchConfig(
            match_id="test-match",
            player_a_id="player_a",
            player_b_id="player_b",
            seed=42,
            best_of=5,
        )
        orch = MatchOrchestrator(config, store)
        events = list(orch.run())
        assert len(events) >= 11  # at least one set (11 points minimum)
        last = events[-1]
        sets_a, sets_b = last.set_scores_after[0], last.set_scores_after[1]
        assert sets_a != sets_b
        sets_needed = sets_to_win_match(5)
        assert sets_a >= sets_needed or sets_b >= sets_needed
        winner_id = config.player_a_id if sets_a >= sets_needed else config.player_b_id
        stats_a, stats_b = aggregate_stats_from_events(
            events,
            winner_id=winner_id,
            player_a_id=config.player_a_id,
            player_b_id=config.player_b_id,
            best_of=5,
        )
        assert stats_a.player_id == "player_a"
        assert stats_b.player_id == "player_b"
        assert stats_a.is_winner != stats_b.is_winner
        score_a = compute_fantasy_score(stats_a)
        score_b = compute_fantasy_score(stats_b)
        assert isinstance(score_a, (int, float))
        assert isinstance(score_b, (int, float))

    def test_events_feed_scoring_correctly(self, db_with_rankings):
        conn = sqlite3.connect(str(db_with_rankings))
        store = build_profile_store_for_match(conn, "player_a", "player_b")
        conn.close()
        config = MatchConfig(
            match_id="test-match-2",
            player_a_id="player_a",
            player_b_id="player_b",
            seed=123,
            best_of=3,
        )
        orch = MatchOrchestrator(config, store)
        events = list(orch.run(max_points=30))
        assert len(events) <= 30
        if not events:
            return
        last = events[-1]
        # Provisional winner from sets so far (may not be match winner if max_points cut off)
        sets_a, sets_b = last.set_scores_after[0], last.set_scores_after[1]
        winner_id = config.player_a_id if sets_a > sets_b else config.player_b_id
        if sets_a == sets_b:
            winner_id = last.outcome.winner_id
        stats_a, stats_b = aggregate_stats_from_events(
            events,
            winner_id=winner_id,
            player_a_id=config.player_a_id,
            player_b_id=config.player_b_id,
            best_of=3,
        )
        assert stats_a.sets_won + stats_a.sets_lost >= 0
        assert stats_b.sets_won + stats_b.sets_lost >= 0
        # Style counts should be non-negative
        assert stats_a.forehand_winners >= 0 and stats_a.backhand_winners >= 0 and stats_a.service_winners >= 0


# ---- Run live match module ----
class TestRunLiveMatch:
    def test_run_live_match_fast_completes(self, sample_rankings_path, tmp_path):
        db_path = tmp_path / "live.db"
        init_db(db_path, sample_rankings_path)
        # Import here to avoid needing backend on path when only running DB tests
        from backend.run_live_match import run
        run(
            seed=999,
            gender="men",
            fast=True,
            rankings_path=sample_rankings_path,
            db_path=db_path,
        )
        # No exception and DB still valid
        conn = sqlite3.connect(str(db_path))
        assert len(list_players_by_gender(conn, "men")) == 2
        conn.close()

    def test_run_live_match_women_fast(self, sample_rankings_path, tmp_path):
        db_path = tmp_path / "live_women.db"
        init_db(db_path, sample_rankings_path)
        from backend.run_live_match import run
        run(
            seed=1000,
            gender="women",
            fast=True,
            rankings_path=sample_rankings_path,
            db_path=db_path,
        )
        conn = sqlite3.connect(str(db_path))
        assert len(list_players_by_gender(conn, "women")) == 2
        conn.close()
