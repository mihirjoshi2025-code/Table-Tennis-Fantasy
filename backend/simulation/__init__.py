"""
AI Match Simulation Engine: deterministic, replayable point-by-point
table-tennis matches for fantasy scoring, narration, and realtime feeds.
"""
from .schemas import (
    PointEvent,
    PointEventOutcome,
    PointOutcome,
    MatchConfig,
    MatchSnapshot,
    ShotType,
    RallyLengthCategory,
    rally_category_from_length,
)
from .profiles import PlayerProfile, ProfileStore, default_profile
from .rng import SeededRNG
from .probability_engine import ProbabilityEngine, MatchContext, OutcomeProbs
from .state_tracker import (
    SetState,
    MomentumState,
    is_pressure_zone,
    is_deciding_set,
)
from .fatigue_model import FatigueModel, FatigueState
from .point_simulator import PointSimulator
from .orchestrator import MatchOrchestrator, set_won, sets_to_win_match
from .emitter import EmitterConfig, SyncEmitter, async_emit_stream, snapshot_from_events
from .persistence import save_replay, load_events, event_to_dict, summarize_match, ReplayMetadata, MatchSummary

__all__ = [
    "PointEvent",
    "PointEventOutcome",
    "PointOutcome",
    "MatchConfig",
    "MatchSnapshot",
    "ShotType",
    "RallyLengthCategory",
    "rally_category_from_length",
    "PlayerProfile",
    "ProfileStore",
    "default_profile",
    "SeededRNG",
    "ProbabilityEngine",
    "MatchContext",
    "OutcomeProbs",
    "SetState",
    "MomentumState",
    "is_pressure_zone",
    "is_deciding_set",
    "FatigueModel",
    "FatigueState",
    "PointSimulator",
    "MatchOrchestrator",
    "set_won",
    "sets_to_win_match",
    "EmitterConfig",
    "SyncEmitter",
    "async_emit_stream",
    "snapshot_from_events",
    "save_replay",
    "load_events",
    "event_to_dict",
    "summarize_match",
    "ReplayMetadata",
    "MatchSummary",
]
