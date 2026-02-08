"""
Database connection and initialization.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from .schema import all_schema_sql


def _run_phase2_migrations(conn: sqlite3.Connection) -> None:
    """Phase 2: add username/password_hash to users; budget to teams; slot/is_captain to team_players."""
    cur = conn.execute("PRAGMA table_info(users)")
    ucols = [row[1] for row in cur.fetchall()]
    if "username" not in ucols:
        conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        conn.execute("UPDATE users SET username = id, password_hash = '' WHERE username IS NULL")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users(username)")
    cur = conn.execute("PRAGMA table_info(teams)")
    tcols = [row[1] for row in cur.fetchall()]
    if "budget" not in tcols:
        conn.execute("ALTER TABLE teams ADD COLUMN budget INTEGER")
    cur = conn.execute("PRAGMA table_info(team_players)")
    tpcols = [row[1] for row in cur.fetchall()]
    if "slot" not in tpcols:
        conn.execute("ALTER TABLE team_players ADD COLUMN slot INTEGER")
        conn.execute("UPDATE team_players SET slot = position WHERE slot IS NULL")
    if "is_captain" not in tpcols:
        conn.execute("ALTER TABLE team_players ADD COLUMN is_captain INTEGER NOT NULL DEFAULT 0")
    # Role system: one role per active player (slots 1-7), at most one per role per team
    if "role" not in tpcols:
        conn.execute("ALTER TABLE team_players ADD COLUMN role TEXT")
    # League-centric: add league_id to teams (one team per user per league)
    cur = conn.execute("PRAGMA table_info(teams)")
    tcols = [row[1] for row in cur.fetchall()]
    if "league_id" not in tcols:
        conn.execute("ALTER TABLE teams ADD COLUMN league_id TEXT REFERENCES leagues(id)")
    # Create indexes on league_id for both newly migrated and fresh DBs (schema no longer creates them)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_teams_league_user ON teams(league_id, user_id) WHERE league_id IS NOT NULL"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_teams_league ON teams(league_id)")


def _run_phase3_league_members(conn: sqlite3.Connection) -> None:
    """Phase 3: league_members join table (league_id, user_id, team_id). One team per user per league."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'league_members'"
    )
    if cur.fetchone() is not None:
        return
    from .schema import league_members_schema
    conn.executescript(league_members_schema())


def _run_phase_leagues_started_at(conn: sqlite3.Connection) -> None:
    """Add started_at to leagues. Set when league is started (frozen); immutable after that."""
    cur = conn.execute("PRAGMA table_info(leagues)")
    cols = [row[1] for row in cur.fetchall()]
    if "started_at" not in cols:
        conn.execute("ALTER TABLE leagues ADD COLUMN started_at TEXT")


def _run_phase_league_matches_started_at(conn: sqlite3.Connection) -> None:
    """Add started_at to league_matches. Set when match goes live; source of truth for late join."""
    cur = conn.execute("PRAGMA table_info(league_matches)")
    cols = [row[1] for row in cur.fetchall()]
    if "started_at" not in cols:
        conn.execute("ALTER TABLE league_matches ADD COLUMN started_at TEXT")


def _run_phase_league_matches_slot_data(conn: sqlite3.Connection) -> None:
    """Add slot_data (JSON) to league_matches. Per-slot TT momentum, analytics, events for completed matches."""
    cur = conn.execute("PRAGMA table_info(league_matches)")
    cols = [row[1] for row in cur.fetchall()]
    if "slot_data" not in cols:
        conn.execute("ALTER TABLE league_matches ADD COLUMN slot_data TEXT")


# Default DB path (project root / data / app.db)
def _default_db_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "app.db"


_db_path: Path | None = None


def set_db_path(path: str | Path) -> None:
    """Set the database path. Call before first get_connection if not using default."""
    global _db_path
    _db_path = Path(path)


def get_db_path() -> Path:
    """Return the current database path."""
    if _db_path is not None:
        return _db_path
    return _default_db_path()


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """
    Return a new SQLite connection.
    Use as context manager or ensure close() is called.
    """
    path = Path(db_path) if db_path else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(
    db_path: str | Path | None = None,
    rankings_path: str | Path | None = None,
) -> None:
    """
    Create or ensure all tables exist.
    If rankings_path is provided, also load players from rankings JSON
    (uses backend.rankings_db).
    """
    path = Path(db_path) if db_path else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        # Players table first (team_players references it)
        from backend.rankings_db import _players_schema, load_rankings_into_db
        conn.executescript(_players_schema())
        # Fantasy tables (users, teams, team_players, matches)
        conn.executescript(all_schema_sql())
        # Migration: add gender to teams if missing (existing DBs)
        cur = conn.execute("PRAGMA table_info(teams)")
        cols = [row[1] for row in cur.fetchall()]
        if "gender" not in cols:
            conn.execute("ALTER TABLE teams ADD COLUMN gender TEXT NOT NULL DEFAULT 'men'")
        # Migration: add salary to players if missing (Phase 2)
        cur = conn.execute("PRAGMA table_info(players)")
        pcols = [row[1] for row in cur.fetchall()]
        if "salary" not in pcols:
            conn.execute("ALTER TABLE players ADD COLUMN salary INTEGER NOT NULL DEFAULT 100")
            conn.execute("UPDATE players SET salary = 70 + CASE WHEN 51 - rank > 80 THEN 80 WHEN 51 - rank < 0 THEN 0 ELSE 51 - rank END")
        _run_phase2_migrations(conn)
        _run_phase3_league_members(conn)
        _run_phase_leagues_started_at(conn)
        _run_phase_league_matches_started_at(conn)
        _run_phase_league_matches_slot_data(conn)
        # Role system: team_players.role added in _run_phase2_migrations
        conn.commit()
        if rankings_path:
            load_rankings_into_db(conn, Path(rankings_path))
            conn.commit()
    finally:
        conn.close()
