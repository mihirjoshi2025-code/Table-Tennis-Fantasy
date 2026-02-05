"""
Database connection and initialization.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from .schema import all_schema_sql


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
        conn.commit()
        if rankings_path:
            load_rankings_into_db(conn, Path(rankings_path))
            conn.commit()
    finally:
        conn.close()
