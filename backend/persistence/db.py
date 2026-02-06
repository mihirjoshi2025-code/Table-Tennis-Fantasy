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
        conn.commit()
        if rankings_path:
            load_rankings_into_db(conn, Path(rankings_path))
            conn.commit()
    finally:
        conn.close()
