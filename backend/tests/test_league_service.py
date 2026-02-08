"""
Tests for league-centric service: status transitions, week sequencing, guards.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.models import LeagueStatus
from backend.persistence.db import get_connection, init_db, set_db_path
from backend.persistence.repositories import (
    LeagueRepository,
    SeasonRepository,
    WeekRepository,
)
from backend.services.league_service import (
    LeagueService,
    LeagueTransitionError,
    WeekSequenceError,
    TeamChangeNotAllowedError,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def db_conn(tmp_path):
    """Temporary DB with schema and leagues/seasons/weeks tables."""
    db_path = tmp_path / "league_test.db"
    set_db_path(db_path)
    init_db(db_path=db_path, rankings_path=PROJECT_ROOT / "data" / "rankings.json")
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def league_service():
    return LeagueService()


@pytest.fixture
def league_and_season(db_conn):
    """Create one league (open) and one season with total_weeks=4."""
    league_repo = LeagueRepository()
    season_repo = SeasonRepository()
    league = league_repo.create(db_conn, "Test League", "user-1", max_teams=8)
    season = season_repo.create(db_conn, league.id, season_number=1, total_weeks=4)
    return league, season


def test_league_status_transition_open_to_locked(db_conn, league_service, league_and_season):
    league, _ = league_and_season
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.LOCKED)
    repo = LeagueRepository()
    updated = repo.get(db_conn, league.id)
    assert updated is not None
    assert updated.status == LeagueStatus.LOCKED


def test_league_status_transition_locked_to_active(db_conn, league_service, league_and_season):
    league, _ = league_and_season
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.LOCKED)
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.ACTIVE)
    repo = LeagueRepository()
    updated = repo.get(db_conn, league.id)
    assert updated.status == LeagueStatus.ACTIVE


def test_league_status_transition_active_to_completed(db_conn, league_service, league_and_season):
    league, _ = league_and_season
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.LOCKED)
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.ACTIVE)
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.COMPLETED)
    repo = LeagueRepository()
    updated = repo.get(db_conn, league.id)
    assert updated.status == LeagueStatus.COMPLETED


def test_league_status_invalid_transition_open_to_completed(db_conn, league_service, league_and_season):
    league, _ = league_and_season
    with pytest.raises(LeagueTransitionError) as exc_info:
        league_service.transition_league_status(db_conn, league.id, LeagueStatus.COMPLETED)
    assert "open" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


def test_league_status_valid_transition_open_to_active(db_conn, league_service, league_and_season):
    """Open -> active is allowed when starting the league (skip locked)."""
    league, _ = league_and_season
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.ACTIVE)
    updated = league_service._league_repo.get(db_conn, league.id)
    assert updated is not None and updated.status == LeagueStatus.ACTIVE


def test_league_status_invalid_transition_completed_to_active(db_conn, league_service, league_and_season):
    league, _ = league_and_season
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.LOCKED)
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.ACTIVE)
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.COMPLETED)
    with pytest.raises(LeagueTransitionError):
        league_service.transition_league_status(db_conn, league.id, LeagueStatus.ACTIVE)


def test_can_simulate_week_only_when_active(db_conn, league_service, league_and_season):
    league, _ = league_and_season
    assert league_service.can_simulate_week(db_conn, league.id) is False
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.LOCKED)
    assert league_service.can_simulate_week(db_conn, league.id) is False
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.ACTIVE)
    assert league_service.can_simulate_week(db_conn, league.id) is True
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.COMPLETED)
    assert league_service.can_simulate_week(db_conn, league.id) is False


def test_can_advance_week_sequential(db_conn, league_service, league_and_season):
    _, season = league_and_season
    # current_week is 1; can advance to 2 only
    assert league_service.can_advance_week(db_conn, season.id, 2) is True
    assert league_service.can_advance_week(db_conn, season.id, 1) is False
    assert league_service.can_advance_week(db_conn, season.id, 3) is False


def test_assert_can_advance_week_raises(db_conn, league_service, league_and_season):
    _, season = league_and_season
    league_service.assert_can_advance_week(db_conn, season.id, 2)
    with pytest.raises(WeekSequenceError):
        league_service.assert_can_advance_week(db_conn, season.id, 5)


def test_can_modify_teams_only_when_open(db_conn, league_service, league_and_season):
    league, _ = league_and_season
    assert league_service.can_modify_teams(db_conn, league.id) is True
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.LOCKED)
    assert league_service.can_modify_teams(db_conn, league.id) is False
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.ACTIVE)
    assert league_service.can_modify_teams(db_conn, league.id) is False


def test_assert_can_modify_teams_raises_when_locked(db_conn, league_service, league_and_season):
    league, _ = league_and_season
    league_service.assert_can_modify_teams(db_conn, league.id)
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.LOCKED)
    with pytest.raises(TeamChangeNotAllowedError):
        league_service.assert_can_modify_teams(db_conn, league.id)


def test_assert_can_simulate_raises_when_not_active(db_conn, league_service, league_and_season):
    league, _ = league_and_season
    with pytest.raises(LeagueTransitionError):
        league_service.assert_can_simulate(db_conn, league.id)
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.LOCKED)
    league_service.transition_league_status(db_conn, league.id, LeagueStatus.ACTIVE)
    league_service.assert_can_simulate(db_conn, league.id)
