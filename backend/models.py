"""
Data models for the fantasy backend.
Domain objects only — no persistence or API logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


# ---------- User ----------
@dataclass
class User:
    """
    A fantasy app user.
    Immutable: id.
    Mutable: name (display name).
    """
    id: str
    name: str
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
        }


# ---------- Player ----------
# Player data lives in rankings_db.players (rankings + simulation stats).
# We reference players by id in teams and matches. No separate Player model
# here; use rankings_db.PlayerRow when reading from DB.


# ---------- Team ----------
@dataclass
class Team:
    """
    A user's fantasy team. Contains multiple players via TeamPlayer.
    Immutable: id, user_id.
    Mutable: name.
    gender: "men" | "women" — must match all selected players.
    """
    id: str
    user_id: str
    name: str
    gender: str  # "men" | "women"
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "gender": self.gender,
            "created_at": self.created_at.isoformat(),
        }


# ---------- TeamPlayer (many-to-many) ----------
@dataclass
class TeamPlayer:
    """
    Links a team to a player. position = 1-based roster order.
    Immutable: team_id, player_id (treat as immutable — delete and re-add to change).
    Mutable: position (reorder).
    """
    team_id: str
    player_id: str
    position: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "player_id": self.player_id,
            "position": self.position,
        }


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
