"""
Tests that team match simulation is deterministic for fixed inputs.
Same seed + same teams => same home_score, away_score, winner_team_id.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.persistence.db import get_connection, init_db, set_db_path
from backend.persistence.repositories import TeamRepository, UserRepository
from backend.services.simulation_service import run_team_match_simulation

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _make_phase2_roster_7_active(player_ids: list[str], captain_index: int = 0) -> list[tuple[str, int, bool, str | None]]:
    """Roster: slots 1-7 active, 8-10 bench; one captain in 1-7; no roles."""
    roster: list[tuple[str, int, bool, str | None]] = []
    for i, pid in enumerate(player_ids[:10]):
        slot = i + 1
        is_captain = i == captain_index and slot <= 7
        roster.append((pid, slot, is_captain, None))
    while len(roster) < 10:
        roster.append((player_ids[-1], len(roster) + 1, False, None))
    return roster[:10]


@pytest.fixture
def db_with_two_teams(tmp_path):
    """DB with rankings and two teams (7 active each) for simulation."""
    db_path = tmp_path / "sim_test.db"
    set_db_path(db_path)
    init_db(db_path=db_path, rankings_path=PROJECT_ROOT / "data" / "rankings.json")
    conn = get_connection()
    try:
        user_repo = UserRepository()
        team_repo = TeamRepository()
        user_repo.create(conn, "User A", id="user-1")
        user_repo.create(conn, "User B", id="user-2")
        # Get 10 men players for each team
        rows = conn.execute(
            "SELECT id FROM players WHERE gender = 'men' ORDER BY rank LIMIT 10"
        ).fetchall()
        player_ids = [r[0] for r in rows]
        if len(player_ids) < 7:
            pytest.skip("Need at least 7 men players in rankings")
        roster_a = _make_phase2_roster_7_active(player_ids[:10], captain_index=0)
        roster_b = _make_phase2_roster_7_active(player_ids[5:15] if len(player_ids) >= 15 else player_ids[:10], captain_index=1)
        team_a = team_repo.create_phase2(
            conn, "user-1", "Team A", "men", budget=100, roster=roster_a, league_id=None
        )
        team_b = team_repo.create_phase2(
            conn, "user-2", "Team B", "men", budget=100, roster=roster_b, league_id=None
        )
        yield conn, team_a.id, team_b.id
    finally:
        conn.close()


def test_team_match_simulation_deterministic(db_with_two_teams):
    """Same seed and same teams produce identical home_score, away_score, winner_team_id."""
    conn, home_id, away_id = db_with_two_teams
    seed = 12345
    result1 = run_team_match_simulation(conn, home_id, away_id, seed=seed, best_of=5)
    result2 = run_team_match_simulation(conn, home_id, away_id, seed=seed, best_of=5)
    assert result1["home_score"] == result2["home_score"]
    assert result1["away_score"] == result2["away_score"]
    assert result1["winner_team_id"] == result2["winner_team_id"]
    assert result1["home_score"] >= 0 and result1["away_score"] >= 0
    assert result1["winner_team_id"] in (home_id, away_id, None)
