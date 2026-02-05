"""
Rankings database: SQLite store of ITTF-style rankings and simulation stats.
Stats defaults are from published research (see docstrings and SOURCES below).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .simulation.profiles import PlayerProfile, ProfileStore

# ---------- Statistics sources (internet / research) ----------
# [1] Serve analyses of elite European table tennis matches: serve directly won 11.6% of points;
#     server scoring advantage; male players show larger serve advantage (Olympic analysis).
# [2] Samson Dubina/Newgy: 56% of points ≤3 shots, 34% on 4-7, 10% 8+ (professional tournament).
# [3] Elite style: backhand stroke position ~55-58% in women (Olympic 2004-2021); serve winner ~11.6%.
#     Style mix (forehand, backhand, service) default 0.45, 0.35, 0.20.
# [4] Clutch / streak / fatigue: small modifiers from existing simulation engine defaults.

DEFAULT_SERVE_MULTIPLIER_MEN = 1.05   # [1] male server advantage slightly higher
DEFAULT_SERVE_MULTIPLIER_WOMEN = 1.04  # [1] female server advantage
DEFAULT_RALLY_SHORT = 0.56   # [2] Newgy/Dubina rally statistics
DEFAULT_RALLY_MEDIUM = 0.34
DEFAULT_RALLY_LONG = 0.10
DEFAULT_STYLE_FOREHAND = 0.45   # [3] elite forehand/backhand/service mix
DEFAULT_STYLE_BACKHAND = 0.35
DEFAULT_STYLE_SERVICE = 0.20
DEFAULT_CLUTCH = 0.03    # [4] pressure situations
DEFAULT_STREAK_BIAS = 0.02
DEFAULT_FATIGUE_SENSITIVITY = 0.5


@dataclass
class PlayerRow:
    """One row from the players table (rankings + simulation stats)."""
    id: str
    name: str
    country: str
    gender: str  # "men" | "women"
    rank: int
    points: int
    serve_multiplier: float
    rally_short_pct: float
    rally_medium_pct: float
    rally_long_pct: float
    style_forehand: float
    style_backhand: float
    style_service: float
    clutch_modifier: float
    streak_bias: float
    fatigue_sensitivity: float

    def to_tuple(self) -> tuple[Any, ...]:
        return (
            self.id,
            self.name,
            self.country,
            self.gender,
            self.rank,
            self.points,
            self.serve_multiplier,
            self.rally_short_pct,
            self.rally_medium_pct,
            self.rally_long_pct,
            self.style_forehand,
            self.style_backhand,
            self.style_service,
            self.clutch_modifier,
            self.streak_bias,
            self.fatigue_sensitivity,
        )


def _slug(name: str) -> str:
    """Stable id from player name (lowercase, spaces to underscores)."""
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def _players_schema() -> str:
    return """
    CREATE TABLE IF NOT EXISTS players (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        country TEXT NOT NULL,
        gender TEXT NOT NULL,
        rank INTEGER NOT NULL,
        points INTEGER NOT NULL,
        serve_multiplier REAL NOT NULL,
        rally_short_pct REAL NOT NULL,
        rally_medium_pct REAL NOT NULL,
        rally_long_pct REAL NOT NULL,
        style_forehand REAL NOT NULL,
        style_backhand REAL NOT NULL,
        style_service REAL NOT NULL,
        clutch_modifier REAL NOT NULL,
        streak_bias REAL NOT NULL,
        fatigue_sensitivity REAL NOT NULL
    );
    """


def init_db(db_path: str | Path, rankings_path: str | Path | None = None) -> None:
    """
    Create or reset the SQLite DB and optionally load from rankings JSON.
    If rankings_path is provided, loads men_singles_rankings and women_singles_rankings.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_players_schema())
        conn.commit()
        if rankings_path is not None:
            load_rankings_into_db(conn, Path(rankings_path))
    finally:
        conn.close()


def load_rankings_into_db(conn: sqlite3.Connection, rankings_path: Path) -> None:
    """Load rankings JSON into the players table. Uses research-based defaults for stats."""
    data = json.loads(rankings_path.read_text())
    men = data.get("men_singles_rankings", [])
    women = data.get("women_singles_rankings", [])
    rows: list[PlayerRow] = []
    for r in men:
        name = r["name"]
        rows.append(PlayerRow(
            id=_slug(name),
            name=name,
            country=r["country"],
            gender="men",
            rank=r["rank"],
            points=r["points"],
            serve_multiplier=DEFAULT_SERVE_MULTIPLIER_MEN,
            rally_short_pct=DEFAULT_RALLY_SHORT,
            rally_medium_pct=DEFAULT_RALLY_MEDIUM,
            rally_long_pct=DEFAULT_RALLY_LONG,
            style_forehand=DEFAULT_STYLE_FOREHAND,
            style_backhand=DEFAULT_STYLE_BACKHAND,
            style_service=DEFAULT_STYLE_SERVICE,
            clutch_modifier=DEFAULT_CLUTCH,
            streak_bias=DEFAULT_STREAK_BIAS,
            fatigue_sensitivity=DEFAULT_FATIGUE_SENSITIVITY,
        ))
    for r in women:
        name = r["name"]
        rows.append(PlayerRow(
            id=_slug(name),
            name=name,
            country=r["country"],
            gender="women",
            rank=r["rank"],
            points=r["points"],
            serve_multiplier=DEFAULT_SERVE_MULTIPLIER_WOMEN,
            rally_short_pct=DEFAULT_RALLY_SHORT,
            rally_medium_pct=DEFAULT_RALLY_MEDIUM,
            rally_long_pct=DEFAULT_RALLY_LONG,
            style_forehand=DEFAULT_STYLE_FOREHAND,
            style_backhand=DEFAULT_STYLE_BACKHAND,
            style_service=DEFAULT_STYLE_SERVICE,
            clutch_modifier=DEFAULT_CLUTCH,
            streak_bias=DEFAULT_STREAK_BIAS,
            fatigue_sensitivity=DEFAULT_FATIGUE_SENSITIVITY,
        ))
    cur = conn.cursor()
    cur.execute("DELETE FROM players")
    for row in rows:
        cur.execute(
            """INSERT OR REPLACE INTO players (
                id, name, country, gender, rank, points,
                serve_multiplier, rally_short_pct, rally_medium_pct, rally_long_pct,
                style_forehand, style_backhand, style_service,
                clutch_modifier, streak_bias, fatigue_sensitivity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            row.to_tuple(),
        )
    conn.commit()


def get_player(conn: sqlite3.Connection, player_id: str) -> PlayerRow | None:
    """Fetch one player by id."""
    cur = conn.execute(
        "SELECT id, name, country, gender, rank, points, "
        "serve_multiplier, rally_short_pct, rally_medium_pct, rally_long_pct, "
        "style_forehand, style_backhand, style_service, "
        "clutch_modifier, streak_bias, fatigue_sensitivity FROM players WHERE id = ?",
        (player_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return PlayerRow(
        id=row[0],
        name=row[1],
        country=row[2],
        gender=row[3],
        rank=row[4],
        points=row[5],
        serve_multiplier=row[6],
        rally_short_pct=row[7],
        rally_medium_pct=row[8],
        rally_long_pct=row[9],
        style_forehand=row[10],
        style_backhand=row[11],
        style_service=row[12],
        clutch_modifier=row[13],
        streak_bias=row[14],
        fatigue_sensitivity=row[15],
    )


def list_players_by_gender(
    conn: sqlite3.Connection,
    gender: str,
    limit: int | None = None,
) -> list[PlayerRow]:
    """List players of one gender, ordered by rank."""
    sql = "SELECT id, name, country, gender, rank, points, " \
          "serve_multiplier, rally_short_pct, rally_medium_pct, rally_long_pct, " \
          "style_forehand, style_backhand, style_service, " \
          "clutch_modifier, streak_bias, fatigue_sensitivity " \
          "FROM players WHERE gender = ? ORDER BY rank"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    cur = conn.execute(sql, (gender,))
    out = []
    for row in cur.fetchall():
        out.append(PlayerRow(
            id=row[0],
            name=row[1],
            country=row[2],
            gender=row[3],
            rank=row[4],
            points=row[5],
            serve_multiplier=row[6],
            rally_short_pct=row[7],
            rally_medium_pct=row[8],
            rally_long_pct=row[9],
            style_forehand=row[10],
            style_backhand=row[11],
            style_service=row[12],
            clutch_modifier=row[13],
            streak_bias=row[14],
            fatigue_sensitivity=row[15],
        ))
    return out


def build_profile_from_row(
    row: PlayerRow,
    opponent_points: int,
    version: str = "v1",
) -> PlayerProfile:
    """
    Build a simulation PlayerProfile from a DB row.
    baseline_point_win is derived from relative points (stronger player > 0.5).
    Other stats come from row (research-based defaults in DB).
    """
    from .simulation.profiles import PlayerProfile
    total = row.points + opponent_points
    if total <= 0:
        base = 0.5
    else:
        # Elo-style: advantage proportional to point difference, clamped
        raw = 0.5 + 0.2 * (row.points - opponent_points) / total
        base = max(0.3, min(0.7, raw))
    # Normalize rally dist and style_mix
    r_sum = row.rally_short_pct + row.rally_medium_pct + row.rally_long_pct
    r_sum = r_sum or 1.0
    rally_dist = (
        row.rally_short_pct / r_sum,
        row.rally_medium_pct / r_sum,
        row.rally_long_pct / r_sum,
    )
    s_sum = row.style_forehand + row.style_backhand + row.style_service
    s_sum = s_sum or 1.0
    style_mix = (
        row.style_forehand / s_sum,
        row.style_backhand / s_sum,
        row.style_service / s_sum,
    )
    return PlayerProfile(
        player_id=row.id,
        version=version,
        baseline_point_win=base,
        serve_multiplier=row.serve_multiplier,
        error_curve={"short": 0.02, "medium": 0.04, "long": 0.08},
        streak_bias=row.streak_bias,
        clutch_modifier=row.clutch_modifier,
        rally_length_dist=rally_dist,
        fatigue_sensitivity=row.fatigue_sensitivity,
        style_mix=style_mix,
    )


def build_profile_store_for_match(
    conn: sqlite3.Connection,
    player_a_id: str,
    player_b_id: str,
    version: str = "v1",
) -> ProfileStore:
    """
    Build a ProfileStore with profiles for both players, with baseline_point_win
    aligned to their relative points (for simulation engine).
    """
    from .simulation.profiles import ProfileStore
    row_a = get_player(conn, player_a_id)
    row_b = get_player(conn, player_b_id)
    if not row_a or not row_b:
        raise ValueError("Both players must exist in DB")
    store = ProfileStore()
    store.put(build_profile_from_row(row_a, row_b.points, version))
    store.put(build_profile_from_row(row_b, row_a.points, version))
    return store
