"""
Seeded RNG for deterministic, replayable simulations.
"""
from __future__ import annotations

import random
from typing import Optional


class SeededRNG:
    """Wrapper around random.Random for reproducible simulations."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._seed = seed

    @property
    def seed(self) -> int | None:
        return self._seed

    def random(self) -> float:
        return self._rng.random()

    def choice(self, seq):
        return self._rng.choice(seq)

    def choices(self, population, weights=None, *, cum_weights=None, k=1):
        return self._rng.choices(population, weights=weights, cum_weights=cum_weights, k=k)

    def randint(self, a: int, b: int) -> int:
        return self._rng.randint(a, b)

    def getstate(self):
        return self._rng.getstate()

    def setstate(self, state) -> None:
        self._rng.setstate(state)
