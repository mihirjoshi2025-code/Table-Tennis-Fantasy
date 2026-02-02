"""
Test suite for the AI Match Simulation Engine.
"""
from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

# Import from backend.simulation (run from project root: python -m pytest backend/tests)
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulation.schemas import (
    PointEvent,
    PointEventOutcome,
    MatchConfig,
    ShotType,
    RallyLengthCategory,
    rally_category_from_length,
)
from simulation.profiles import PlayerProfile, ProfileStore, default_profile
from simulation.rng import SeededRNG
from simulation.state_tracker import (
    SetState,
    MomentumState,
    is_pressure_zone,
    is_deciding_set,
)
from simulation.fatigue_model import FatigueModel, FatigueState, f_rally, g_set
from simulation.probability_engine import ProbabilityEngine, MatchContext, OutcomeProbs
from simulation.point_simulator import PointSimulator, sample_shot_type, sample_rally_category
from simulation.orchestrator import MatchOrchestrator, set_won, sets_to_win_match
from simulation.emitter import EmitterConfig, SyncEmitter, snapshot_from_events
from simulation.persistence import save_replay, load_events, event_to_dict, summarize_match, ReplayMetadata


# ---- Schemas ----
class TestSchemas:
    def test_rally_category_from_length(self):
        assert rally_category_from_length(1) == RallyLengthCategory.SHORT
        assert rally_category_from_length(3) == RallyLengthCategory.SHORT
        assert rally_category_from_length(4) == RallyLengthCategory.MEDIUM
        assert rally_category_from_length(7) == RallyLengthCategory.MEDIUM
        assert rally_category_from_length(8) == RallyLengthCategory.LONG
        assert rally_category_from_length(15) == RallyLengthCategory.LONG

    def test_match_config(self):
        cfg = MatchConfig(match_id="m1", player_a_id="a", player_b_id="b", seed=42)
        assert cfg.games_to_win_set == 11
        assert cfg.win_by == 2
        assert cfg.best_of == 5


# ---- RNG ----
class TestSeededRNG:
    def test_determinism(self):
        rng1 = SeededRNG(12345)
        rng2 = SeededRNG(12345)
        for _ in range(100):
            assert rng1.random() == rng2.random()
        assert rng1.randint(1, 10) == rng2.randint(1, 10)

    def test_choice(self):
        rng = SeededRNG(999)
        choices = [rng.choice([1, 2, 3]) for _ in range(20)]
        assert all(c in [1, 2, 3] for c in choices)


# ---- Profiles ----
class TestProfiles:
    def test_default_profile(self):
        p = default_profile("player1", version="v1")
        assert p.player_id == "player1"
        assert 0.3 <= p.baseline_point_win <= 0.7
        assert p.serve_multiplier >= 1.0
        assert len(p.style_mix) == 3
        assert abs(sum(p.style_mix) - 1.0) < 0.01

    def test_profile_store_put_get(self):
        store = ProfileStore()
        p = default_profile("alice")
        store.put(p)
        assert store.get("alice") is p
        assert store.get("bob") is None

    def test_profile_serialization(self):
        p = default_profile("x", version="v2")
        d = p.to_dict()
        p2 = PlayerProfile.from_dict(d)
        assert p2.player_id == p.player_id
        assert p2.baseline_point_win == p.baseline_point_win
        assert p2.style_mix == p.style_mix


# ---- State tracker ----
class TestStateTracker:
    def test_set_state(self):
        s = SetState(5, 7, 12)
        assert s.score() == (5, 7)
        s.games_a += 1
        assert s.score() == (6, 7)

    def test_momentum_record(self):
        m = MomentumState(window_size=5)
        m.record_point(True)
        m.record_point(True)
        assert m.streak_a == 2
        assert m.streak_b == 0
        m.record_point(False)
        assert m.streak_a == 0
        assert m.streak_b == 1

    def test_momentum_score_bounds(self):
        m = MomentumState()
        for _ in range(20):
            m.record_point(True)
        assert -1.0 <= m.momentum_score_a() <= 1.0
        m2 = MomentumState()
        for _ in range(20):
            m2.record_point(False)
        assert -1.0 <= m2.momentum_score_a() <= 1.0

    def test_is_pressure_zone(self):
        assert is_pressure_zone(9, 9, 11, 2) is True
        assert is_pressure_zone(10, 10, 11, 2) is True
        assert is_pressure_zone(5, 5, 11, 2) is False
        assert is_pressure_zone(11, 9, 11, 2) is True

    def test_is_deciding_set(self):
        # Deciding set = last possible set (e.g. set index 2 in best of 3, index 4 in best of 5)
        assert is_deciding_set(2, 3) is True
        assert is_deciding_set(1, 3) is False
        assert is_deciding_set(4, 5) is True
        assert is_deciding_set(0, 5) is False

    def test_set_won(self):
        # set_won from orchestrator (games_a, games_b, to_win, win_by). Win by 2 required.
        assert set_won(11, 5, 11, 2) == "a"
        assert set_won(5, 11, 11, 2) == "b"
        assert set_won(11, 10, 11, 2) is None  # 11-10 is not win by 2
        assert set_won(12, 10, 11, 2) == "a"
        assert set_won(10, 12, 11, 2) == "b"
        assert set_won(10, 10, 11, 2) is None
        assert set_won(9, 8, 11, 2) is None


# ---- Fatigue ----
class TestFatigueModel:
    def test_f_rally(self):
        assert f_rally(1) < f_rally(5)
        assert f_rally(5) < f_rally(10)

    def test_fatigue_state_clamp(self):
        f = FatigueState(level=0.5)
        f.level = 1.5
        f.clamp()
        assert f.level == 1.0
        f.level = -0.2
        f.clamp()
        assert f.level == 0.0

    def test_fatigue_penalty(self):
        assert FatigueModel.fatigue_penalty(0.0) == 1.0
        assert FatigueModel.fatigue_penalty(1.0) < 1.0
        assert FatigueModel.fatigue_penalty(1.0) >= 0.7

    def test_update_and_recover(self):
        model = FatigueModel(w_rally=1.0, w_set=0.5, recovery_between_sets=0.3)
        fa, fb = FatigueState(), FatigueState()
        model.update_after_point(fa, fb, rally_length=10, points_in_set_a=20, points_in_set_b=18, sensitivity_a=0.5, sensitivity_b=0.5)
        assert fa.level > 0 or fb.level > 0
        model.recover_between_sets(fa, fb)
        assert fa.level < 0.3  # recovered some


# ---- Probability engine ----
class TestProbabilityEngine:
    def test_compute_probs_sum_to_one(self):
        engine = ProbabilityEngine()
        pa = default_profile("a")
        pb = default_profile("b")
        mom = MomentumState()
        ctx = MatchContext(
            server_id="a",
            games_a=5,
            games_b=5,
            set_index=0,
            best_of=5,
            momentum=mom,
            fatigue_a=0.0,
            fatigue_b=0.0,
            points_in_set=10,
        )
        probs = engine.compute(pa, pb, ctx, "a", "b")
        assert abs(probs.p_a_wins + probs.p_b_wins - 1.0) < 0.001
        assert 0 <= probs.p_a_wins <= 1
        assert 0 <= probs.p_b_wins <= 1

    def test_serve_advantage(self):
        engine = ProbabilityEngine()
        pa = default_profile("a")
        pb = default_profile("b")
        mom = MomentumState()
        ctx_a_serves = MatchContext("a", 5, 5, 0, 5, mom, 0.0, 0.0, 10)
        ctx_b_serves = MatchContext("b", 5, 5, 0, 5, mom, 0.0, 0.0, 10)
        probs_a = engine.compute(pa, pb, ctx_a_serves, "a", "b")
        probs_b = engine.compute(pa, pb, ctx_b_serves, "a", "b")
        # A's win prob should be higher when A serves (same baseline)
        assert probs_a.p_a_wins > probs_b.p_a_wins


# ---- Point simulator ----
class TestPointSimulator:
    def test_sample_point_deterministic_with_same_seed(self):
        rng1 = SeededRNG(42)
        rng2 = SeededRNG(42)
        engine = ProbabilityEngine()
        sim1 = PointSimulator(engine, rng1)
        sim2 = PointSimulator(engine, rng2)
        pa = default_profile("a")
        pb = default_profile("b")
        mom = MomentumState()
        ctx = MatchContext("a", 0, 0, 0, 5, mom, 0.0, 0.0, 0)
        o1, r1, _ = sim1.sample_point(pa, pb, ctx, "a", "b")
        o2, r2, _ = sim2.sample_point(pa, pb, ctx, "a", "b")
        assert o1.winner_id == o2.winner_id
        assert o1.shot_type == o2.shot_type
        assert r1 == r2

    def test_sample_shot_type(self):
        rng = SeededRNG(0)
        shot = sample_shot_type(rng, (0.5, 0.3, 0.2))
        assert shot in (ShotType.FOREHAND, ShotType.BACKHAND, ShotType.SERVICE)

    def test_sample_rally_category(self):
        rng = SeededRNG(0)
        cat = sample_rally_category(rng, (0.33, 0.33, 0.34))
        assert cat in (RallyLengthCategory.SHORT, RallyLengthCategory.MEDIUM, RallyLengthCategory.LONG)


def _store_and_config():
    """Shared fixture data: store with alice/bob, and match config."""
    store = ProfileStore()
    store.put(default_profile("alice", elo_advantage=0.02))
    store.put(default_profile("bob", elo_advantage=-0.02))
    config = MatchConfig(match_id="test-match", player_a_id="alice", player_b_id="bob", seed=123, best_of=3)
    return store, config


# ---- Orchestrator ----
class TestMatchOrchestrator:
    @pytest.fixture
    def store_and_config(self):
        return _store_and_config()

    def test_orchestrator_produces_events(self, store_and_config):
        store, config = store_and_config
        orch = MatchOrchestrator(config, store)
        events = list(orch.run(max_points=50))
        assert len(events) >= 1
        assert len(events) <= 50
        e0 = events[0]
        assert e0.match_id == config.match_id
        assert e0.point_index == 1
        assert e0.outcome.winner_id in (config.player_a_id, config.player_b_id)
        assert e0.rally_length >= 1
        assert e0.score_after[0] + e0.score_after[1] >= 1

    def test_orchestrator_full_match_deterministic(self, store_and_config):
        store, config = store_and_config
        config.seed = 456
        orch1 = MatchOrchestrator(config, store)
        orch2 = MatchOrchestrator(config, store)
        events1 = list(orch1.run())
        events2 = list(orch2.run())
        assert len(events1) == len(events2)
        for e1, e2 in zip(events1, events2):
            assert e1.point_index == e2.point_index
            assert e1.outcome.winner_id == e2.outcome.winner_id
            assert e1.score_after == e2.score_after

    def test_orchestrator_set_progression(self, store_and_config):
        store, config = store_and_config
        orch = MatchOrchestrator(config, store)
        events = list(orch.run())
        last = events[-1]
        assert len(last.set_scores_after) >= 2
        # Match should complete: one player has won majority of sets
        sets_a, sets_b = last.set_scores_after[0], last.set_scores_after[1]
        assert sets_a != sets_b or (sets_a + sets_b) >= 2
        assert last.set_index >= 0

    def test_sets_to_win_match(self):
        assert sets_to_win_match(3) == 2
        assert sets_to_win_match(5) == 3


# ---- Emitter ----
class TestEmitter:
    def test_fast_forward_emits_immediately(self):
        store = ProfileStore()
        store.put(default_profile("a"))
        store.put(default_profile("b"))
        config = MatchConfig(match_id="m", player_a_id="a", player_b_id="b", seed=1)
        orch = MatchOrchestrator(config, store)
        events = list(orch.run(max_points=5))
        cfg = EmitterConfig(fast_forward=True)
        emitted = []
        emitter = SyncEmitter(cfg)
        emitter.emit_stream(iter(events), on_event=emitted.append)
        assert len(emitted) == len(events)


# ---- Persistence ----
class TestPersistence:
    def test_save_and_load_replay(self):
        store, config = _store_and_config()
        orch = MatchOrchestrator(config, store)
        events = list(orch.run(max_points=30))
        with tempfile.TemporaryDirectory() as tmp:
            save_replay(events, config, {"alice": "v1", "bob": "v1"}, tmp)
            meta, loaded = load_events(config.match_id, tmp)
            assert meta.seed == config.seed
            assert meta.event_count == len(events)
            assert len(loaded) == len(events)
            assert loaded[0]["outcome"]["winner_id"] == events[0].outcome.winner_id

    def test_event_to_dict(self):
        e = PointEvent(
            match_id="m",
            point_index=1,
            set_index=0,
            game_index=0,
            score_before=(0, 0),
            score_after=(1, 0),
            set_scores_before=(0, 0),
            set_scores_after=(0, 0),
            server_id="a",
            outcome=PointEventOutcome(winner_id="a", loser_id="b", shot_type="forehand"),
            rally_length=5,
            rally_category="medium",
        )
        d = event_to_dict(e)
        assert d["match_id"] == "m"
        assert d["outcome"]["winner_id"] == "a"

    def test_summarize_match(self):
        store, config = _store_and_config()
        orch = MatchOrchestrator(config, store)
        events = list(orch.run(max_points=25))
        if not events:
            return
        last = events[-1]
        winner = last.outcome.winner_id  # last point winner; for full match use orchestrator winner
        summary = summarize_match(events, winner)
        assert summary.total_points == len(events)
        assert summary.avg_rally_length >= 1


# ---- Integration: run short match and snapshot ----
class TestIntegration:
    def test_run_short_match_and_snapshot(self):
        store = ProfileStore()
        store.put(default_profile("player_a"))
        store.put(default_profile("player_b"))
        config = MatchConfig(match_id="int-1", player_a_id="player_a", player_b_id="player_b", seed=777, best_of=3)
        orch = MatchOrchestrator(config, store)
        events = []
        for ev in orch.run(max_points=20):
            events.append(ev)
        snap = snapshot_from_events(events, config.match_id)
        assert snap is not None
        assert snap.point_index == events[-1].point_index
        assert snap.set_scores == events[-1].set_scores_after
        assert snap.current_game_score == events[-1].score_after
