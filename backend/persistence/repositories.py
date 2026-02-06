"""
Repository interfaces for fantasy data.
No business logic — only read/write operations.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import Any

from backend.models import User, Team, TeamPlayer, Match, TeamMatch, League, Season, Week, LeagueMatch


def _parse_datetime(s: str | None) -> datetime:
    if s is None:
        raise ValueError("expected datetime string")
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------- UserRepository ----------


class UserRepository:
    """CRUD for users. Phase 2: username, password_hash for auth."""

    def create(self, conn: sqlite3.Connection, name: str, id: str | None = None) -> User:
        uid = id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        cols = "id, name, created_at"
        vals = "?, ?, ?"
        args: tuple = (uid, name, now)
        if _has_col(conn, "users", "username"):
            cols += ", username, password_hash"
            vals += ", ?, ?"
            args = args + (uid, "")
        conn.execute(f"INSERT INTO users ({cols}) VALUES ({vals})", args)
        conn.commit()
        return self.get(conn, uid) or User(id=uid, name=name, created_at=datetime.fromisoformat(now))

    def create_with_password(
        self, conn: sqlite3.Connection, username: str, password_hash: str, name: str | None = None
    ) -> User:
        if not _has_col(conn, "users", "username"):
            raise RuntimeError("Phase 2 migration missing: users table has no username column")
        uid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        display_name = name or username
        conn.execute(
            "INSERT INTO users (id, username, password_hash, name, created_at) VALUES (?, ?, ?, ?, ?)",
            (uid, username, password_hash, display_name, now),
        )
        conn.commit()
        return self.get(conn, uid) or User(
            id=uid, name=display_name, created_at=datetime.fromisoformat(now),
            username=username, password_hash=password_hash,
        )

    def get(self, conn: sqlite3.Connection, user_id: str) -> User | None:
        cols = "id, name, created_at"
        if _has_col(conn, "users", "username"):
            cols += ", username, password_hash"
        row = conn.execute(f"SELECT {cols} FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        r = dict(row)
        username = r.get("username")
        phash = r.get("password_hash")
        return User(
            id=r["id"],
            name=r["name"],
            created_at=_parse_datetime(r["created_at"]),
            username=username,
            password_hash=phash,
        )

    def get_by_username(self, conn: sqlite3.Connection, username: str) -> User | None:
        cur = conn.execute(
            "SELECT id, name, created_at, username, password_hash FROM users WHERE username = ?",
            (username,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return User(
            id=row[0],
            name=row[1],
            created_at=_parse_datetime(row[2]),
            username=row[3],
            password_hash=row[4],
        )

    def list_all(self, conn: sqlite3.Connection) -> list[User]:
        rows = conn.execute("SELECT id, name, created_at FROM users ORDER BY created_at").fetchall()
        return [
            User(id=r["id"], name=r["name"], created_at=_parse_datetime(r["created_at"]))
            for r in rows
        ]


def _has_col(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return col in [row[1] for row in cur.fetchall()]


# ---------- LeagueRepository ----------


class LeagueRepository:
    """CRUD for leagues. No business logic."""

    def create(
        self,
        conn: sqlite3.Connection,
        name: str,
        owner_id: str,
        max_teams: int,
        id: str | None = None,
    ) -> League:
        lid = id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO leagues (id, name, owner_id, status, max_teams, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (lid, name, owner_id, "open", max_teams, now),
        )
        conn.commit()
        return League(
            id=lid, name=name, owner_id=owner_id, status="open", max_teams=max_teams,
            created_at=datetime.fromisoformat(now),
        )

    def get(self, conn: sqlite3.Connection, league_id: str) -> League | None:
        row = conn.execute(
            "SELECT id, name, owner_id, status, max_teams, created_at FROM leagues WHERE id = ?",
            (league_id,),
        ).fetchone()
        if row is None:
            return None
        return League(
            id=row["id"],
            name=row["name"],
            owner_id=row["owner_id"],
            status=row["status"],
            max_teams=row["max_teams"],
            created_at=_parse_datetime(row["created_at"]),
        )

    def update_status(self, conn: sqlite3.Connection, league_id: str, status: str) -> None:
        conn.execute("UPDATE leagues SET status = ? WHERE id = ?", (status, league_id))
        conn.commit()


# ---------- SeasonRepository ----------


class SeasonRepository:
    """CRUD for seasons. No business logic."""

    def create(
        self,
        conn: sqlite3.Connection,
        league_id: str,
        season_number: int,
        total_weeks: int,
        id: str | None = None,
    ) -> Season:
        sid = id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO seasons (id, league_id, season_number, current_week, total_weeks, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (sid, league_id, season_number, 1, total_weeks, now),
        )
        conn.commit()
        return Season(
            id=sid, league_id=league_id, season_number=season_number,
            current_week=1, total_weeks=total_weeks, created_at=datetime.fromisoformat(now),
        )

    def get(self, conn: sqlite3.Connection, season_id: str) -> Season | None:
        row = conn.execute(
            "SELECT id, league_id, season_number, current_week, total_weeks, created_at FROM seasons WHERE id = ?",
            (season_id,),
        ).fetchone()
        if row is None:
            return None
        return Season(
            id=row["id"],
            league_id=row["league_id"],
            season_number=row["season_number"],
            current_week=row["current_week"],
            total_weeks=row["total_weeks"],
            created_at=_parse_datetime(row["created_at"]),
        )

    def get_current_for_league(self, conn: sqlite3.Connection, league_id: str) -> Season | None:
        row = conn.execute(
            "SELECT id, league_id, season_number, current_week, total_weeks, created_at FROM seasons WHERE league_id = ? ORDER BY season_number DESC LIMIT 1",
            (league_id,),
        ).fetchone()
        if row is None:
            return None
        return Season(
            id=row["id"],
            league_id=row["league_id"],
            season_number=row["season_number"],
            current_week=row["current_week"],
            total_weeks=row["total_weeks"],
            created_at=_parse_datetime(row["created_at"]),
        )

    def update_current_week(self, conn: sqlite3.Connection, season_id: str, current_week: int) -> None:
        conn.execute("UPDATE seasons SET current_week = ? WHERE id = ?", (current_week, season_id))
        conn.commit()


# ---------- WeekRepository ----------


class WeekRepository:
    """CRUD for weeks. No business logic."""

    def create(
        self,
        conn: sqlite3.Connection,
        season_id: str,
        week_number: int,
        id: str | None = None,
    ) -> Week:
        wid = id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO weeks (id, season_id, week_number, status, started_at, completed_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (wid, season_id, week_number, "pending", None, None, now),
        )
        conn.commit()
        return Week(
            id=wid, season_id=season_id, week_number=week_number, status="pending",
            started_at=None, completed_at=None, created_at=datetime.fromisoformat(now),
        )

    def get(self, conn: sqlite3.Connection, week_id: str) -> Week | None:
        row = conn.execute(
            "SELECT id, season_id, week_number, status, started_at, completed_at, created_at FROM weeks WHERE id = ?",
            (week_id,),
        ).fetchone()
        if row is None:
            return None
        return Week(
            id=row["id"],
            season_id=row["season_id"],
            week_number=row["week_number"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=_parse_datetime(row["created_at"]),
        )

    def get_by_season_and_number(self, conn: sqlite3.Connection, season_id: str, week_number: int) -> Week | None:
        row = conn.execute(
            "SELECT id, season_id, week_number, status, started_at, completed_at, created_at FROM weeks WHERE season_id = ? AND week_number = ?",
            (season_id, week_number),
        ).fetchone()
        if row is None:
            return None
        return Week(
            id=row["id"],
            season_id=row["season_id"],
            week_number=row["week_number"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=_parse_datetime(row["created_at"]),
        )

    def list_by_season(self, conn: sqlite3.Connection, season_id: str) -> list[Week]:
        rows = conn.execute(
            "SELECT id, season_id, week_number, status, started_at, completed_at, created_at FROM weeks WHERE season_id = ? ORDER BY week_number",
            (season_id,),
        ).fetchall()
        return [
            Week(
                id=r["id"],
                season_id=r["season_id"],
                week_number=r["week_number"],
                status=r["status"],
                started_at=r["started_at"],
                completed_at=r["completed_at"],
                created_at=_parse_datetime(r["created_at"]),
            )
            for r in rows
        ]

    def update_status(self, conn: sqlite3.Connection, week_id: str, status: str, started_at: str | None = None, completed_at: str | None = None) -> None:
        if started_at is not None and completed_at is not None:
            conn.execute("UPDATE weeks SET status = ?, started_at = ?, completed_at = ? WHERE id = ?", (status, started_at, completed_at, week_id))
        elif started_at is not None:
            conn.execute("UPDATE weeks SET status = ?, started_at = ? WHERE id = ?", (status, started_at, week_id))
        elif completed_at is not None:
            conn.execute("UPDATE weeks SET status = ?, completed_at = ? WHERE id = ?", (status, completed_at, week_id))
        else:
            conn.execute("UPDATE weeks SET status = ? WHERE id = ?", (status, week_id))
        conn.commit()


# ---------- LeagueMatchRepository ----------


class LeagueMatchRepository:
    """CRUD for league_matches (fixtures). No business logic."""

    def create(
        self,
        conn: sqlite3.Connection,
        week_id: str,
        home_team_id: str,
        away_team_id: str | None,
        id: str | None = None,
    ) -> LeagueMatch:
        mid = id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO league_matches (id, week_id, home_team_id, away_team_id, home_score, away_score, status, simulation_log, created_at) VALUES (?, ?, ?, ?, 0, 0, 'scheduled', NULL, ?)",
            (mid, week_id, home_team_id, away_team_id, now),
        )
        conn.commit()
        return LeagueMatch(
            id=mid, week_id=week_id, home_team_id=home_team_id, away_team_id=away_team_id,
            home_score=0.0, away_score=0.0, status="scheduled", simulation_log=None,
            created_at=datetime.fromisoformat(now),
        )

    def get(self, conn: sqlite3.Connection, league_match_id: str) -> LeagueMatch | None:
        row = conn.execute(
            "SELECT id, week_id, home_team_id, away_team_id, home_score, away_score, status, simulation_log, created_at FROM league_matches WHERE id = ?",
            (league_match_id,),
        ).fetchone()
        if row is None:
            return None
        return LeagueMatch(
            id=row["id"],
            week_id=row["week_id"],
            home_team_id=row["home_team_id"],
            away_team_id=row["away_team_id"],
            home_score=row["home_score"],
            away_score=row["away_score"],
            status=row["status"],
            simulation_log=row["simulation_log"],
            created_at=_parse_datetime(row["created_at"]),
        )

    def list_by_week(self, conn: sqlite3.Connection, week_id: str) -> list[LeagueMatch]:
        rows = conn.execute(
            "SELECT id, week_id, home_team_id, away_team_id, home_score, away_score, status, simulation_log, created_at FROM league_matches WHERE week_id = ? ORDER BY id",
            (week_id,),
        ).fetchall()
        return [
            LeagueMatch(
                id=r["id"],
                week_id=r["week_id"],
                home_team_id=r["home_team_id"],
                away_team_id=r["away_team_id"],
                home_score=r["home_score"],
                away_score=r["away_score"],
                status=r["status"],
                simulation_log=r["simulation_log"],
                created_at=_parse_datetime(r["created_at"]),
            )
            for r in rows
        ]

    def update_result(
        self,
        conn: sqlite3.Connection,
        league_match_id: str,
        home_score: float,
        away_score: float,
        simulation_log: str | None = None,
    ) -> None:
        conn.execute(
            "UPDATE league_matches SET home_score = ?, away_score = ?, status = 'completed', simulation_log = ? WHERE id = ?",
            (home_score, away_score, simulation_log, league_match_id),
        )
        conn.commit()


# ---------- TeamRepository ----------


class TeamRepository:
    """CRUD for teams and team_players. Phase 2: budget, slot, is_captain."""

    def create(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        name: str,
        gender: str,
        player_ids: list[str],
        id: str | None = None,
        budget: int | None = None,
        league_id: str | None = None,
    ) -> Team:
        tid = id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        cols, vals, args = ["id", "user_id", "name", "gender", "created_at"], ["?", "?", "?", "?", "?"], [tid, user_id, name, gender, now]
        if _has_col(conn, "teams", "budget") and budget is not None:
            cols.append("budget"); vals.append("?"); args.append(budget)
        if _has_col(conn, "teams", "league_id"):
            cols.append("league_id"); vals.append("?"); args.append(league_id)
        conn.execute(f"INSERT INTO teams ({', '.join(cols)}) VALUES ({', '.join(vals)})", args)
        for pos, pid in enumerate(player_ids, start=1):
            if _has_col(conn, "team_players", "slot"):
                conn.execute(
                    "INSERT INTO team_players (team_id, player_id, position, slot, is_captain) VALUES (?, ?, ?, ?, ?)",
                    (tid, pid, pos, pos, 0),
                )
            else:
                conn.execute(
                    "INSERT INTO team_players (team_id, player_id, position) VALUES (?, ?, ?)",
                    (tid, pid, pos),
                )
        conn.commit()
        return Team(
            id=tid, user_id=user_id, name=name, gender=gender,
            created_at=datetime.fromisoformat(now), budget=budget, league_id=league_id,
        )

    def create_phase2(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        name: str,
        gender: str,
        budget: int,
        roster: list[tuple[str, int, bool]],  # (player_id, slot, is_captain)
        id: str | None = None,
        league_id: str | None = None,
    ) -> Team:
        """Phase 2: 10 players, slots 1-7 active 8-10 bench, one captain in 1-7. Optional league_id."""
        tid = id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        cols, vals, args = ["id", "user_id", "name", "gender", "budget", "created_at"], ["?", "?", "?", "?", "?", "?"], [tid, user_id, name, gender, budget, now]
        if _has_col(conn, "teams", "league_id"):
            cols.append("league_id"); vals.append("?"); args.append(league_id)
        conn.execute(f"INSERT INTO teams ({', '.join(cols)}) VALUES ({', '.join(vals)})", args)
        for pos, (pid, slot, is_captain) in enumerate(roster, start=1):
            conn.execute(
                "INSERT INTO team_players (team_id, player_id, position, slot, is_captain) VALUES (?, ?, ?, ?, ?)",
                (tid, pid, pos, slot, 1 if is_captain else 0),
            )
        conn.commit()
        return Team(
            id=tid, user_id=user_id, name=name, gender=gender,
            created_at=datetime.fromisoformat(now), budget=budget, league_id=league_id,
        )

    def get(self, conn: sqlite3.Connection, team_id: str) -> Team | None:
        cols = "id, user_id, name, gender, created_at"
        if _has_col(conn, "teams", "budget"):
            cols += ", budget"
        if _has_col(conn, "teams", "league_id"):
            cols += ", league_id"
        row = conn.execute(f"SELECT {cols} FROM teams WHERE id = ?", (team_id,)).fetchone()
        if row is None:
            return None
        r = dict(row)
        return Team(
            id=r["id"],
            user_id=r["user_id"],
            name=r["name"],
            gender=r["gender"] if "gender" in r.keys() else "men",
            created_at=_parse_datetime(r["created_at"]),
            budget=r.get("budget"),
            league_id=r.get("league_id"),
        )

    def get_players(self, conn: sqlite3.Connection, team_id: str) -> list[str]:
        """Return player_ids for team, ordered by position."""
        rows = conn.execute(
            "SELECT player_id FROM team_players WHERE team_id = ? ORDER BY position",
            (team_id,),
        ).fetchall()
        return [r["player_id"] for r in rows]

    def get_players_with_slots(
        self, conn: sqlite3.Connection, team_id: str
    ) -> list[tuple[str, int, bool]]:
        """Phase 2: (player_id, slot, is_captain) ordered by position."""
        if not _has_col(conn, "team_players", "slot"):
            ids = self.get_players(conn, team_id)
            return [(pid, i, False) for i, pid in enumerate(ids, start=1)]
        rows = conn.execute(
            "SELECT player_id, slot, is_captain FROM team_players WHERE team_id = ? ORDER BY position",
            (team_id,),
        ).fetchall()
        return [(r["player_id"], r["slot"], bool(r["is_captain"])) for r in rows]

    def get_active_player_ids(self, conn: sqlite3.Connection, team_id: str) -> list[str]:
        """Phase 2: player_ids for slots 1-7 only."""
        with_slots = self.get_players_with_slots(conn, team_id)
        return [pid for pid, slot, _ in with_slots if 1 <= slot <= 7]

    def get_captain_id(self, conn: sqlite3.Connection, team_id: str) -> str | None:
        """Phase 2: player_id who is captain."""
        with_slots = self.get_players_with_slots(conn, team_id)
        for pid, _, is_captain in with_slots:
            if is_captain:
                return pid
        return None

    def list_by_user(self, conn: sqlite3.Connection, user_id: str) -> list[Team]:
        cols = "id, user_id, name, gender, created_at"
        if _has_col(conn, "teams", "budget"):
            cols += ", budget"
        if _has_col(conn, "teams", "league_id"):
            cols += ", league_id"
        rows = conn.execute(
            f"SELECT {cols} FROM teams WHERE user_id = ? ORDER BY created_at",
            (user_id,),
        ).fetchall()
        return [
            Team(
                id=r["id"],
                user_id=r["user_id"],
                name=r["name"],
                gender=r["gender"] if "gender" in r.keys() else "men",
                created_at=_parse_datetime(r["created_at"]),
                budget=r.get("budget"),
                league_id=r.get("league_id") if _has_col(conn, "teams", "league_id") else None,
            )
            for r in rows
        ]

    def get_by_league_and_user(self, conn: sqlite3.Connection, league_id: str, user_id: str) -> Team | None:
        """One team per user per league. Returns None if no team in that league."""
        if not _has_col(conn, "teams", "league_id"):
            return None
        cols = "id, user_id, name, gender, created_at, budget, league_id"
        row = conn.execute(
            f"SELECT {cols} FROM teams WHERE league_id = ? AND user_id = ?",
            (league_id, user_id),
        ).fetchone()
        if row is None:
            return None
        r = dict(row)
        return Team(
            id=r["id"], user_id=r["user_id"], name=r["name"],
            gender=r["gender"] if r.get("gender") else "men",
            created_at=_parse_datetime(r["created_at"]),
            budget=r.get("budget"), league_id=r.get("league_id"),
        )

    def list_by_league(self, conn: sqlite3.Connection, league_id: str) -> list[Team]:
        """All teams registered to a league."""
        if not _has_col(conn, "teams", "league_id"):
            return []
        cols = "id, user_id, name, gender, created_at, budget, league_id"
        rows = conn.execute(
            f"SELECT {cols} FROM teams WHERE league_id = ? ORDER BY created_at",
            (league_id,),
        ).fetchall()
        return [
            Team(
                id=r["id"], user_id=r["user_id"], name=r["name"],
                gender=r["gender"] if r.get("gender") else "men",
                created_at=_parse_datetime(r["created_at"]),
                budget=r.get("budget"), league_id=r.get("league_id"),
            )
            for r in rows
        ]


# ---------- TeamMatchRepository (Phase 2) ----------


class TeamMatchRepository:
    """CRUD for team_matches (aggregate 7v7 with captain bonus)."""

    def create(
        self,
        conn: sqlite3.Connection,
        team_a_id: str,
        team_b_id: str,
        score_a: float,
        score_b: float,
        captain_a_id: str | None,
        captain_b_id: str | None,
        id: str | None = None,
    ) -> TeamMatch:
        tid = id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO team_matches (
                id, team_a_id, team_b_id, score_a, score_b,
                captain_a_id, captain_b_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (tid, team_a_id, team_b_id, score_a, score_b, captain_a_id, captain_b_id, now),
        )
        conn.commit()
        return TeamMatch(
            id=tid,
            team_a_id=team_a_id,
            team_b_id=team_b_id,
            score_a=score_a,
            score_b=score_b,
            captain_a_id=captain_a_id,
            captain_b_id=captain_b_id,
            created_at=datetime.fromisoformat(now),
        )

    def get(self, conn: sqlite3.Connection, team_match_id: str) -> TeamMatch | None:
        row = conn.execute(
            """SELECT id, team_a_id, team_b_id, score_a, score_b,
                      captain_a_id, captain_b_id, created_at
               FROM team_matches WHERE id = ?""",
            (team_match_id,),
        ).fetchone()
        if row is None:
            return None
        return TeamMatch(
            id=row["id"],
            team_a_id=row["team_a_id"],
            team_b_id=row["team_b_id"],
            score_a=row["score_a"],
            score_b=row["score_b"],
            captain_a_id=row["captain_a_id"],
            captain_b_id=row["captain_b_id"],
            created_at=_parse_datetime(row["created_at"]),
        )


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

    def get_most_recent_for_player(
        self, conn: sqlite3.Connection, player_id: str
    ) -> Match | None:
        """Return the most recent match where this player participated (as player_a or player_b)."""
        row = conn.execute(
            """SELECT id, team_a_id, team_b_id, player_a_id, player_b_id,
                      winner_id, sets_a, sets_b, best_of, seed, created_at, events_json
               FROM matches
               WHERE player_a_id = ? OR player_b_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (player_id, player_id),
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
