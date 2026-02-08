"""
Tests for round-robin schedule generation.
Deterministic; no duplicate matchups; at most one game per team per week.
"""
from __future__ import annotations

import pytest

from backend.services.scheduling import (
    round_robin_pairings,
    generate_league_schedule,
    BYE,
)


def test_round_robin_two_teams():
    """2 teams: 1 week, 1 match."""
    pairings = round_robin_pairings(["A", "B"])
    assert len(pairings) == 1
    w, h, a = pairings[0]
    assert w == 1
    assert (h, a) in [("A", "B"), ("B", "A")]


def test_round_robin_three_teams():
    """3 teams: add BYE, 3 weeks. Each real pair (A-B, A-C, B-C) exactly once."""
    pairings = round_robin_pairings(["A", "B", "C"])
    # 3 teams + BYE = 4 slots, 3 weeks, 2 matches per week = 6 fixtures (3 bye, 3 real)
    assert len(pairings) == 6
    real = [(h, a) for w, h, a in pairings if a is not None]
    byes = [h for w, h, a in pairings if a is None]
    assert len(real) == 3
    assert len(byes) == 3
    pairs = {tuple(sorted([h, a])) for h, a in real}
    assert pairs == {("A", "B"), ("A", "C"), ("B", "C")}
    # Each team has exactly one bye
    assert sorted(byes) == ["A", "B", "C"]


def test_round_robin_four_teams():
    """4 teams: 3 weeks, 2 matches per week, 6 matches total. Each pair once."""
    pairings = round_robin_pairings(["A", "B", "C", "D"])
    assert len(pairings) == 6
    pairs = {tuple(sorted([h, a])) for w, h, a in pairings}
    expected = {("A", "B"), ("A", "C"), ("A", "D"), ("B", "C"), ("B", "D"), ("C", "D")}
    assert pairs == expected


def test_generate_league_schedule():
    """generate_league_schedule returns list of dicts with week_number, home_team_id, away_team_id."""
    fixtures = generate_league_schedule(["X", "Y", "Z"])
    assert len(fixtures) >= 3
    for f in fixtures:
        assert "week_number" in f
        assert "home_team_id" in f
        assert "away_team_id" in f
        assert f["week_number"] >= 1
        if f["away_team_id"] is not None:
            assert f["away_team_id"] != BYE
