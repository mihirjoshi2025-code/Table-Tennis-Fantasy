"""
Real-Time Illusion Layer (Emitter): separates simulation time from emission time.
Configurable scheduler: emit point events at X–Y seconds, pauses between sets,
fast-forward for batch or live pacing for UI/WebSocket.
"""
from __future__ import annotations

import time
import asyncio
from typing import AsyncIterator, Callable, Iterator
from dataclasses import dataclass

from .schemas import PointEvent, MatchSnapshot


@dataclass
class EmitterConfig:
    """Emission timing."""
    min_seconds_per_point: float = 2.0
    max_seconds_per_point: float = 5.0
    pause_between_sets_seconds: float = 30.0
    fast_forward: bool = False  # if True, emit immediately (batch)


def _point_delay(config: EmitterConfig, rng) -> float:
    if config.fast_forward:
        return 0.0
    return rng.uniform(config.min_seconds_per_point, config.max_seconds_per_point)


class SyncEmitter:
    """
    Consumes a stream of PointEvents and re-emits them with optional delays.
    Blocking (sync); for async use AsyncEmitter or run in executor.
    """

    def __init__(self, config: EmitterConfig | None = None) -> None:
        self.config = config or EmitterConfig()
        import random
        self._rng = random.Random()

    def emit_stream(
        self,
        event_iterator: Iterator[PointEvent],
        on_event: Callable[[PointEvent], None],
        on_pause_set: Callable[[], None] | None = None,
    ) -> None:
        """Consume events and call on_event (and on_pause_set between sets) with delays."""
        prev_set = -1
        for event in event_iterator:
            if event.set_index != prev_set and prev_set >= 0:
                if on_pause_set:
                    on_pause_set()
                if not self.config.fast_forward and self.config.pause_between_sets_seconds > 0:
                    time.sleep(self.config.pause_between_sets_seconds)
            delay = _point_delay(self.config, self._rng)
            if delay > 0:
                time.sleep(delay)
            on_event(event)
            prev_set = event.set_index


async def async_emit_stream(
    event_iterator: Iterator[PointEvent],
    config: EmitterConfig | None = None,
    on_event: Callable[[PointEvent], None] | None = None,
) -> AsyncIterator[PointEvent]:
    """
    Async generator: yields PointEvents with delays between them.
    Suitable for WebSocket or async consumers.
    """
    cfg = config or EmitterConfig()
    import random
    rng = random.Random()
    prev_set = -1
    for event in event_iterator:
        if event.set_index != prev_set and prev_set >= 0:
            if not cfg.fast_forward and cfg.pause_between_sets_seconds > 0:
                await asyncio.sleep(cfg.pause_between_sets_seconds)
        delay = _point_delay(cfg, rng)
        if delay > 0:
            await asyncio.sleep(delay)
        if on_event:
            on_event(event)
        yield event
        prev_set = event.set_index


def snapshot_from_events(events: list[PointEvent], match_id: str) -> MatchSnapshot | None:
    """Build a MatchSnapshot from the last event in a list."""
    if not events:
        return None
    e = events[-1]
    return MatchSnapshot(
        match_id=match_id,
        point_index=e.point_index,
        set_index=e.set_index,
        game_index=e.game_index,
        set_scores=e.set_scores_after,
        current_game_score=e.score_after,
        server_id=e.server_id,
        completed=False,
        winner_id=None,
        events_count=len(events),
    )
