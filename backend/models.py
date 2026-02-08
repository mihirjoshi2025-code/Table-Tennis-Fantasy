"""
Data models for the fantasy backend.
Domain objects only — no persistence or API logic.

League-centric architecture: users participate in leagues; leagues have seasons;
seasons have weeks; matches happen as time advances (not on-demand).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


# ---------- League status (state machine) ----------
class LeagueStatus(str, Enum):
    """League lifecycle: open → locked → active → completed."""
    OPEN = "open"       # Accepting teams
    LOCKED = "locked"  # Started, no more team changes
    ACTIVE = "active"  # Matches in progress
    COMPLETED = "completed"  # All weeks done


# ---------- Week status ----------
class WeekStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"


# ---------- League match (fixture) status ----------
class LeagueMatchStatus(str, Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    COMPLETED = "completed"


# ---------- User ----------
@dataclass
class User:
    """
    A fantasy app user.
    Phase 2: username (unique, for login), password_hash (never plain text).
    """
    id: str
    name: str
    created_at: datetime
    username: str | None = None
    password_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
        }
        if self.username is not None:
            d["username"] = self.username
        return d


# ---------- Player ----------
# Player data lives in rankings_db.players (rankings + simulation stats).
# We reference players by id in teams and matches. No separate Player model
# here; use rankings_db.PlayerRow when reading from DB.


# ---------- LeagueMember (join: league_id, user_id, team_id) ----------
@dataclass
class LeagueMember:
    """
    One user's membership in a league with one team. One team per user per league.
    """
    league_id: str
    user_id: str
    team_id: str
    joined_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "league_id": self.league_id,
            "user_id": self.user_id,
            "team_id": self.team_id,
            "joined_at": self.joined_at.isoformat(),
        }


# ---------- League ----------
@dataclass
class League:
    """
    Multiplayer competition container. Owns seasons and state.
    Status: open (draft) → active → completed.
    started_at set when league is frozen; no more teams or roster changes.
    """
    id: str
    name: str
    owner_id: str
    status: str  # LeagueStatus value
    max_teams: int
    created_at: datetime
    started_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "owner_id": self.owner_id,
            "status": self.status,
            "max_teams": self.max_teams,
            "created_at": self.created_at.isoformat(),
        }
        if self.started_at is not None:
            d["started_at"] = self.started_at.isoformat()
        return d


# ---------- Season ----------
@dataclass
class Season:
    """
    One season within a league. Owns weeks and current_week.
    Future-proofing for multi-season leagues.
    """
    id: str
    league_id: str
    season_number: int
    current_week: int  # 1-based
    total_weeks: int
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "league_id": self.league_id,
            "season_number": self.season_number,
            "current_week": self.current_week,
            "total_weeks": self.total_weeks,
            "created_at": self.created_at.isoformat(),
        }


# ---------- Week ----------
@dataclass
class Week:
    """
    Time progression unit. Only one week may be active per season at a time.
    status: pending | completed.
    """
    id: str
    season_id: str
    week_number: int
    status: str  # WeekStatus value
    started_at: str | None
    completed_at: str | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "season_id": self.season_id,
            "week_number": self.week_number,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "created_at": self.created_at.isoformat(),
        }


# ---------- LeagueMatch (fixture) ----------
@dataclass
class LeagueMatch:
    """
    A scheduled or completed team-vs-team match within a week.
    Created by the league system; simulation runs when week is executed.
    away_team_id is nullable for bye weeks.
    """
    id: str
    week_id: str
    home_team_id: str
    away_team_id: str | None
    home_score: float
    away_score: float
    status: str  # LeagueMatchStatus value
    simulation_log: str | None  # explanation or log
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "week_id": self.week_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }
        if self.simulation_log is not None:
            d["simulation_log"] = self.simulation_log
        return d


# ---------- Team ----------
@dataclass
class Team:
    """
    A user's fantasy team, registered to a league. Phase 2: budget.
    One team per user per league. Teams cannot exist outside a league context.
    """
    id: str
    user_id: str
    name: str
    gender: str  # "men" | "women"
    created_at: datetime
    budget: int | None = None
    league_id: str | None = None  # Required for league-driven flow; nullable for legacy

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "gender": self.gender,
            "created_at": self.created_at.isoformat(),
        }
        if self.budget is not None:
            d["budget"] = self.budget
        if self.league_id is not None:
            d["league_id"] = self.league_id
        return d


# ---------- TeamPlayer (many-to-many) ----------
@dataclass
class TeamPlayer:
    """
    Links a team to a player. Phase 2: slot 1-7 = active, 8-10 = bench; is_captain (one of 1-7).
    """
    team_id: str
    player_id: str
    position: int
    slot: int | None = None  # 1-7 active, 8-10 bench
    is_captain: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "team_id": self.team_id,
            "player_id": self.player_id,
            "position": self.position,
        }
        if self.slot is not None:
            d["slot"] = self.slot
        d["is_captain"] = self.is_captain
        return d


# ---------- TeamMatch (Phase 2) ----------
@dataclass
class TeamMatch:
    """Phase 2: aggregate team-vs-team match (7 active players, captain bonus)."""
    id: str
    team_a_id: str
    team_b_id: str
    score_a: float
    score_b: float
    captain_a_id: str | None
    captain_b_id: str | None
    created_at: datetime


# ---------- Match ----------
@dataclass
class Match:
    """
    A match between two teams. Stores basic metadata.
    player_a_id, player_b_id = the actual players who competed (one per team).
    Immutable after creation: id, team_a_id, team_b_id, player_a_id, player_b_id,
    winner_id, sets_a, sets_b, best_of, seed.
    """
    id: str
    team_a_id: str
    team_b_id: str
    player_a_id: str
    player_b_id: str
    winner_id: str  # player_id who won
    sets_a: int
    sets_b: int
    best_of: int
    seed: int
    created_at: datetime
    events_json: str | None = None  # optional: serialized point events for replay

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "team_a_id": self.team_a_id,
            "team_b_id": self.team_b_id,
            "player_a_id": self.player_a_id,
            "player_b_id": self.player_b_id,
            "winner_id": self.winner_id,
            "sets_a": self.sets_a,
            "sets_b": self.sets_b,
            "best_of": self.best_of,
            "seed": self.seed,
            "created_at": self.created_at.isoformat(),
        }
        if self.events_json is not None:
            d["events_json"] = self.events_json
        return d
