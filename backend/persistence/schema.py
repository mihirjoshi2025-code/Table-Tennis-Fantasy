"""
SQLite schema for fantasy entities.
Migration-friendly: each table created with IF NOT EXISTS.
"""
from __future__ import annotations


def users_schema() -> str:
    return """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """


def teams_schema() -> str:
    return """
    CREATE TABLE IF NOT EXISTS teams (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        gender TEXT NOT NULL DEFAULT 'men',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """


def team_players_schema() -> str:
    return """
    CREATE TABLE IF NOT EXISTS team_players (
        team_id TEXT NOT NULL,
        player_id TEXT NOT NULL,
        position INTEGER NOT NULL,
        PRIMARY KEY (team_id, player_id),
        FOREIGN KEY (team_id) REFERENCES teams(id),
        FOREIGN KEY (player_id) REFERENCES players(id)
    );
    CREATE INDEX IF NOT EXISTS ix_team_players_team_id ON team_players(team_id);
    CREATE INDEX IF NOT EXISTS ix_team_players_player_id ON team_players(player_id);
    """


def matches_schema() -> str:
    return """
    CREATE TABLE IF NOT EXISTS matches (
        id TEXT PRIMARY KEY,
        team_a_id TEXT NOT NULL,
        team_b_id TEXT NOT NULL,
        player_a_id TEXT NOT NULL,
        player_b_id TEXT NOT NULL,
        winner_id TEXT NOT NULL,
        sets_a INTEGER NOT NULL,
        sets_b INTEGER NOT NULL,
        best_of INTEGER NOT NULL,
        seed INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        events_json TEXT,
        FOREIGN KEY (team_a_id) REFERENCES teams(id),
        FOREIGN KEY (team_b_id) REFERENCES teams(id),
        FOREIGN KEY (player_a_id) REFERENCES players(id),
        FOREIGN KEY (player_b_id) REFERENCES players(id)
    );
    CREATE INDEX IF NOT EXISTS ix_matches_team_a ON matches(team_a_id);
    CREATE INDEX IF NOT EXISTS ix_matches_team_b ON matches(team_b_id);
    CREATE INDEX IF NOT EXISTS ix_matches_created_at ON matches(created_at);
    """


def all_schema_sql() -> str:
    """Combine all schema DDL for a single execution."""
    return "\n".join([
        users_schema(),
        teams_schema(),
        team_players_schema(),
        matches_schema(),
    ])
