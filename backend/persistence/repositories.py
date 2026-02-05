"""
Repository interfaces for fantasy data.
No business logic — only read/write operations.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import Any

from backend.models import User, Team, TeamPlayer, Match


def _parse_datetime(s: str | None) -> datetime:
    if s is None:
        raise ValueError("expected datetime string")
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------- UserRepository ----------


class UserRepository:
    """CRUD for users."""

    def create(self, conn: sqlite3.Connection, name: str, id: str | None = None) -> User:
        uid = id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO users (id, name, created_at) VALUES (?, ?, ?)",
            (uid, name, now),
        )
        conn.commit()
        return User(id=uid, name=name, created_at=datetime.fromisoformat(now))

    def get(self, conn: sqlite3.Connection, user_id: str) -> User | None:
        row = conn.execute("SELECT id, name, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return User(
            id=row["id"],
            name=row["name"],
            created_at=_parse_datetime(row["created_at"]),
        )

    def list_all(self, conn: sqlite3.Connection) -> list[User]:
        rows = conn.execute("SELECT id, name, created_at FROM users ORDER BY created_at").fetchall()
        return [
            User(id=r["id"], name=r["name"], created_at=_parse_datetime(r["created_at"]))
            for r in rows
        ]


# ---------- TeamRepository ----------


class TeamRepository:
    """CRUD for teams and team_players."""

    def create(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        name: str,
        player_ids: list[str],
        id: str | None = None,
    ) -> Team:
        tid = id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO teams (id, user_id, name, created_at) VALUES (?, ?, ?, ?)",
            (tid, user_id, name, now),
        )
        for pos, pid in enumerate(player_ids, start=1):
            conn.execute(
                "INSERT INTO team_players (team_id, player_id, position) VALUES (?, ?, ?)",
                (tid, pid, pos),
            )
        conn.commit()
        return Team(id=tid, user_id=user_id, name=name, created_at=datetime.fromisoformat(now))

    def get(self, conn: sqlite3.Connection, team_id: str) -> Team | None:
        row = conn.execute(
            "SELECT id, user_id, name, created_at FROM teams WHERE id = ?",
            (team_id,),
        ).fetchone()
        if row is None:
            return None
        return Team(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            created_at=_parse_datetime(row["created_at"]),
        )

    def get_players(self, conn: sqlite3.Connection, team_id: str) -> list[str]:
        """Return player_ids for team, ordered by position."""
        rows = conn.execute(
            "SELECT player_id FROM team_players WHERE team_id = ? ORDER BY position",
            (team_id,),
        ).fetchall()
        return [r["player_id"] for r in rows]

    def list_by_user(self, conn: sqlite3.Connection, user_id: str) -> list[Team]:
        rows = conn.execute(
            "SELECT id, user_id, name, created_at FROM teams WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        ).fetchall()
        return [
            Team(
                id=r["id"],
                user_id=r["user_id"],
                name=r["name"],
                created_at=_parse_datetime(r["created_at"]),
            )
            for r in rows
        ]


# ---------- MatchRepository ----------


class MatchRepository:
    """CRUD for matches."""

    def create(
        self,
        conn: sqlite3.Connection,
        team_a_id: str,
        team_b_id: str,
        player_a_id: str,
        player_b_id: str,
        winner_id: str,
        sets_a: int,
        sets_b: int,
        best_of: int,
        seed: int,
        events_json: str | None = None,
        id: str | None = None,
    ) -> Match:
        mid = id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO matches (
                id, team_a_id, team_b_id, player_a_id, player_b_id,
                winner_id, sets_a, sets_b, best_of, seed, created_at, events_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mid,
                team_a_id,
                team_b_id,
                player_a_id,
                player_b_id,
                winner_id,
                sets_a,
                sets_b,
                best_of,
                seed,
                now,
                events_json,
            ),
        )
        conn.commit()
        return Match(
            id=mid,
            team_a_id=team_a_id,
            team_b_id=team_b_id,
            player_a_id=player_a_id,
            player_b_id=player_b_id,
            winner_id=winner_id,
            sets_a=sets_a,
            sets_b=sets_b,
            best_of=best_of,
            seed=seed,
            created_at=datetime.fromisoformat(now),
            events_json=events_json,
        )

    def get(self, conn: sqlite3.Connection, match_id: str) -> Match | None:
        row = conn.execute(
            """SELECT id, team_a_id, team_b_id, player_a_id, player_b_id,
                      winner_id, sets_a, sets_b, best_of, seed, created_at, events_json
               FROM matches WHERE id = ?""",
            (match_id,),
        ).fetchone()
        if row is None:
            return None
        return Match(
            id=row["id"],
            team_a_id=row["team_a_id"],
            team_b_id=row["team_b_id"],
            player_a_id=row["player_a_id"],
            player_b_id=row["player_b_id"],
            winner_id=row["winner_id"],
            sets_a=row["sets_a"],
            sets_b=row["sets_b"],
            best_of=row["best_of"],
            seed=row["seed"],
            created_at=_parse_datetime(row["created_at"]),
            events_json=row["events_json"],
        )

    def list_recent(self, conn: sqlite3.Connection, limit: int = 50) -> list[Match]:
        rows = conn.execute(
            """SELECT id, team_a_id, team_b_id, player_a_id, player_b_id,
                      winner_id, sets_a, sets_b, best_of, seed, created_at, events_json
               FROM matches ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            Match(
                id=r["id"],
                team_a_id=r["team_a_id"],
                team_b_id=r["team_b_id"],
                player_a_id=r["player_a_id"],
                player_b_id=r["player_b_id"],
                winner_id=r["winner_id"],
                sets_a=r["sets_a"],
                sets_b=r["sets_b"],
                best_of=r["best_of"],
                seed=r["seed"],
                created_at=_parse_datetime(r["created_at"]),
                events_json=r["events_json"],
            )
            for r in rows
        ]
