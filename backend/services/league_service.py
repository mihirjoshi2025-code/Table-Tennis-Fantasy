"""
League-centric service: state machine, guards, week sequencing, scheduling.
Start league: generate round-robin schedule. Fast-forward week: run all matches, advance.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from backend.models import LeagueStatus
from backend.persistence.repositories import (
    LeagueRepository,
    LeagueMemberRepository,
    SeasonRepository,
    WeekRepository,
    LeagueMatchRepository,
    TeamRepository,
)
from backend.services.scheduling import generate_league_schedule
from backend.services.simulation_service import run_team_match_simulation

# ---------- Exceptions ----------


class LeagueTransitionError(ValueError):
    """Invalid league status transition (e.g. open -> completed)."""


class WeekSequenceError(ValueError):
    """Weeks must be sequential; cannot advance out of order."""


class TeamChangeNotAllowedError(ValueError):
    """Cannot modify teams after league is locked."""


# ---------- Valid transitions ----------

_VALID_TRANSITIONS: dict[str, set[str]] = {
    LeagueStatus.OPEN: {LeagueStatus.LOCKED, LeagueStatus.ACTIVE},  # Start league: open -> active (skip locked)
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
        self._member_repo = LeagueMemberRepository()
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

    # ---------- Start league & scheduling ----------

    def start_league(self, conn: sqlite3.Connection, league_id: str) -> None:
        """
        Transition open -> locked -> active, create season, generate round-robin schedule.
        Uses league_members' team_ids. Each team must have exactly 7 active players.
        """
        league = self._league_repo.get(conn, league_id)
        if league is None:
            raise ValueError(f"League not found: {league_id}")
        if league.status != LeagueStatus.OPEN:
            raise LeagueTransitionError(f"League must be open to start (current: {league.status})")
        members = self._member_repo.list_by_league(conn, league_id)
        team_ids = [m.team_id for m in members]
        if len(team_ids) < 2:
            raise ValueError("Need at least 2 teams to start a league")
        # Ensure each team has 7 active (slots 1-7)
        for tid in team_ids:
            active = self._team_repo.get_active_player_ids(conn, tid)
            if len(active) != 7:
                raise ValueError(f"Team {tid} must have exactly 7 active players (slots 1-7)")
        fixtures = generate_league_schedule(team_ids)
        if not fixtures:
            raise ValueError("Schedule generation produced no fixtures")
        weeks_set = {f["week_number"] for f in fixtures}
        total_weeks = max(weeks_set)
        # Create season and weeks
        season = self._season_repo.create(
            conn, league_id, season_number=1, total_weeks=total_weeks
        )
        week_ids_by_number: dict[int, str] = {}
        for w in range(1, total_weeks + 1):
            week = self._week_repo.create(conn, season.id, w)
            week_ids_by_number[w] = week.id
        for f in fixtures:
            wnum = f["week_number"]
            week_id = week_ids_by_number[wnum]
            self._league_match_repo.create(
                conn, week_id,
                home_team_id=f["home_team_id"],
                away_team_id=f["away_team_id"],
            )
        # Freeze league: status = active, started_at = now. No more teams or roster changes.
        now_iso = datetime.now(timezone.utc).isoformat()
        self._league_repo.update_status(conn, league_id, LeagueStatus.ACTIVE)
        self._league_repo.update_started_at(conn, league_id, now_iso)

    def fast_forward_week(
        self, conn: sqlite3.Connection, league_id: str, seed: int | None = None
    ) -> None:
        """
        Run all pending matches for the current week, persist results, mark week completed,
        advance season current_week. If no more weeks, transition league to completed.
        Demo mode: deterministic if seed provided.
        """
        league = self._league_repo.get(conn, league_id)
        if league is None:
            raise ValueError(f"League not found: {league_id}")
        if league.status != LeagueStatus.ACTIVE:
            raise LeagueTransitionError(f"League must be active to fast-forward (current: {league.status})")
        season = self._season_repo.get_current_for_league(conn, league_id)
        if season is None:
            raise ValueError("No season for league")
        week = self._week_repo.get_by_season_and_number(conn, season.id, season.current_week)
        if week is None:
            raise ValueError(f"Week {season.current_week} not found")
        matches = self._league_match_repo.list_by_week(conn, week.id)
        for m in matches:
            if m.status == "completed":
                continue
            if m.away_team_id is None:
                # Bye: home wins by default (0-0 or no points)
                self._league_match_repo.update_result(
                    conn, m.id, 0.0, 0.0, simulation_log="Bye"
                )
                continue
            result = run_team_match_simulation(
                conn, m.home_team_id, m.away_team_id, seed=seed, best_of=5
            )
            self._league_match_repo.update_result(
                conn, m.id,
                result["home_score"], result["away_score"],
                simulation_log=result.get("explanation"),
            )
        now = datetime.now(timezone.utc).isoformat()
        self._week_repo.update_status(conn, week.id, "completed", completed_at=now)
        next_week = season.current_week + 1
        if next_week > season.total_weeks:
            self._league_repo.update_status(conn, league_id, LeagueStatus.COMPLETED)
        else:
            self._season_repo.update_current_week(conn, season.id, next_week)
