"""
League-centric service: state machine, guards, week sequencing.
No scheduling or gameplay UI; foundational logic for future phases.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from backend.models import LeagueStatus
from backend.persistence.repositories import (
    LeagueRepository,
    SeasonRepository,
    WeekRepository,
    LeagueMatchRepository,
    TeamRepository,
)

# ---------- Exceptions ----------


class LeagueTransitionError(ValueError):
    """Invalid league status transition (e.g. open -> completed)."""


class WeekSequenceError(ValueError):
    """Weeks must be sequential; cannot advance out of order."""


class TeamChangeNotAllowedError(ValueError):
    """Cannot modify teams after league is locked."""


# ---------- Valid transitions ----------

_VALID_TRANSITIONS: dict[str, set[str]] = {
    LeagueStatus.OPEN: {LeagueStatus.LOCKED},
    LeagueStatus.LOCKED: {LeagueStatus.ACTIVE},
    LeagueStatus.ACTIVE: {LeagueStatus.COMPLETED},
    LeagueStatus.COMPLETED: set(),
}


# ---------- LeagueService ----------


class LeagueService:
    """
    Domain logic for leagues: status transitions, week sequencing, guards.
    Persistence is delegated to repositories.
    """

    def __init__(self) -> None:
        self._league_repo = LeagueRepository()
        self._season_repo = SeasonRepository()
        self._week_repo = WeekRepository()
        self._league_match_repo = LeagueMatchRepository()
        self._team_repo = TeamRepository()

    def transition_league_status(self, conn: sqlite3.Connection, league_id: str, new_status: str) -> None:
        """
        Transition league to new_status if valid.
        Valid: open -> locked -> active -> completed.
        """
        league = self._league_repo.get(conn, league_id)
        if league is None:
            raise ValueError(f"League not found: {league_id}")
        current = league.status
        allowed = _VALID_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise LeagueTransitionError(
                f"Invalid transition: {current} -> {new_status}. Allowed from {current}: {allowed}"
            )
        self._league_repo.update_status(conn, league_id, new_status)

    def can_simulate_week(self, conn: sqlite3.Connection, league_id: str) -> bool:
        """Simulation is only allowed when league is active."""
        league = self._league_repo.get(conn, league_id)
        return league is not None and league.status == LeagueStatus.ACTIVE

    def can_advance_week(self, conn: sqlite3.Connection, season_id: str, to_week_number: int) -> bool:
        """
        Weeks must be sequential. Only one week may be active at a time.
        Returns True if advancing to to_week_number is valid (current_week + 1 == to_week_number).
        """
        season = self._season_repo.get(conn, season_id)
        if season is None:
            return False
        return season.current_week + 1 == to_week_number

    def can_modify_teams(self, conn: sqlite3.Connection, league_id: str) -> bool:
        """Teams cannot be modified after league is locked."""
        league = self._league_repo.get(conn, league_id)
        return league is not None and league.status == LeagueStatus.OPEN

    def assert_can_simulate(self, conn: sqlite3.Connection, league_id: str) -> None:
        """Raise if simulation is not allowed (league must be active)."""
        if not self.can_simulate_week(conn, league_id):
            league = self._league_repo.get(conn, league_id)
            status = league.status if league else "not found"
            raise LeagueTransitionError(f"Cannot simulate: league must be active (current: {status})")

    def assert_can_advance_week(self, conn: sqlite3.Connection, season_id: str, to_week_number: int) -> None:
        """Raise if advancing to to_week_number is invalid (weeks must be sequential)."""
        if not self.can_advance_week(conn, season_id, to_week_number):
            season = self._season_repo.get(conn, season_id)
            current = season.current_week if season else 0
            raise WeekSequenceError(
                f"Cannot advance to week {to_week_number}: current week is {current}; weeks must be sequential"
            )

    def assert_can_modify_teams(self, conn: sqlite3.Connection, league_id: str) -> None:
        """Raise if team changes are not allowed (league must be open)."""
        if not self.can_modify_teams(conn, league_id):
            league = self._league_repo.get(conn, league_id)
            status = league.status if league else "not found"
            raise TeamChangeNotAllowedError(
                f"Cannot modify teams: league must be open (current: {status})"
            )

    # ---------- TODOs for future phases ----------
    # TODO: run_week_simulation(conn, week_id) — run all league_matches for the week using simulation_service, persist results, mark week completed.
    # TODO: generate_schedule(conn, season_id) — create league_matches for all weeks (schedule generation).
    # TODO: start_league(conn, league_id) — transition open -> locked, create season if needed.
    # TODO: start_week(conn, week_id) — mark week started, transition league to active if first week.
