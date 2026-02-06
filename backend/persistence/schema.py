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
    # Phase 2 columns username, password_hash added via migration


def leagues_schema() -> str:
    """League-centric: multiplayer competition container. status: open | locked | active | completed."""
    return """
    CREATE TABLE IF NOT EXISTS leagues (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        max_teams INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (owner_id) REFERENCES users(id)
    );
    CREATE INDEX IF NOT EXISTS ix_leagues_owner ON leagues(owner_id);
    CREATE INDEX IF NOT EXISTS ix_leagues_status ON leagues(status);
    """


def seasons_schema() -> str:
    """One season per league. Owns current_week and total_weeks."""
    return """
    CREATE TABLE IF NOT EXISTS seasons (
        id TEXT PRIMARY KEY,
        league_id TEXT NOT NULL,
        season_number INTEGER NOT NULL,
        current_week INTEGER NOT NULL DEFAULT 1,
        total_weeks INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (league_id) REFERENCES leagues(id)
    );
    CREATE INDEX IF NOT EXISTS ix_seasons_league ON seasons(league_id);
    """


def weeks_schema() -> str:
    """Time progression. status: pending | completed. Only one active week per season."""
    return """
    CREATE TABLE IF NOT EXISTS weeks (
        id TEXT PRIMARY KEY,
        season_id TEXT NOT NULL,
        week_number INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        started_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (season_id) REFERENCES seasons(id)
    );
    CREATE INDEX IF NOT EXISTS ix_weeks_season ON weeks(season_id);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_weeks_season_number ON weeks(season_id, week_number);
    """


def league_matches_schema() -> str:
    """Fixture within a week. Created by league system; simulation when week runs. away_team_id NULL = bye."""
    return """
    CREATE TABLE IF NOT EXISTS league_matches (
        id TEXT PRIMARY KEY,
        week_id TEXT NOT NULL,
        home_team_id TEXT NOT NULL,
        away_team_id TEXT,
        home_score REAL NOT NULL DEFAULT 0,
        away_score REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'scheduled',
        simulation_log TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (week_id) REFERENCES weeks(id),
        FOREIGN KEY (home_team_id) REFERENCES teams(id),
        FOREIGN KEY (away_team_id) REFERENCES teams(id)
    );
    CREATE INDEX IF NOT EXISTS ix_league_matches_week ON league_matches(week_id);
    CREATE INDEX IF NOT EXISTS ix_league_matches_home ON league_matches(home_team_id);
    CREATE INDEX IF NOT EXISTS ix_league_matches_away ON league_matches(away_team_id);
    """


def team_matches_schema() -> str:
    """Phase 2: aggregate team-vs-team match (7 active players, captain bonus)."""
    return """
    CREATE TABLE IF NOT EXISTS team_matches (
        id TEXT PRIMARY KEY,
        team_a_id TEXT NOT NULL,
        team_b_id TEXT NOT NULL,
        score_a REAL NOT NULL,
        score_b REAL NOT NULL,
        captain_a_id TEXT,
        captain_b_id TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (team_a_id) REFERENCES teams(id),
        FOREIGN KEY (team_b_id) REFERENCES teams(id)
    );
    CREATE INDEX IF NOT EXISTS ix_team_matches_team_a ON team_matches(team_a_id);
    CREATE INDEX IF NOT EXISTS ix_team_matches_team_b ON team_matches(team_b_id);
    """


def teams_schema() -> str:
    """Teams belong to a league. One team per user per league. league_id added via migration for existing DBs."""
    return """
    CREATE TABLE IF NOT EXISTS teams (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        league_id TEXT,
        name TEXT NOT NULL,
        gender TEXT NOT NULL DEFAULT 'men',
        budget INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (league_id) REFERENCES leagues(id)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS ix_teams_league_user ON teams(league_id, user_id) WHERE league_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS ix_teams_league ON teams(league_id);
    """


def team_players_schema() -> str:
    return """
    CREATE TABLE IF NOT EXISTS team_players (
        team_id TEXT NOT NULL,
        player_id TEXT NOT NULL,
        position INTEGER NOT NULL,
        slot INTEGER,
        is_captain INTEGER NOT NULL DEFAULT 0,
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
    """Combine all schema DDL for a single execution. Order: users, leagues, teams, seasons, weeks, league_matches, team_players, matches, team_matches."""
    return "\n".join([
        users_schema(),
        leagues_schema(),
        teams_schema(),
        seasons_schema(),
        weeks_schema(),
        league_matches_schema(),
        team_players_schema(),
        matches_schema(),
        team_matches_schema(),
    ])
