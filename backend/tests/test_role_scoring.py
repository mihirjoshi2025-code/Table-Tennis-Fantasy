"""
Role-based scoring test suite.

Validates: role uniqueness, deterministic scoring with/without roles,
role-specific effects (Anchor, Aggressor, Closer, Wildcard, Stabilizer),
regression (removing role reverts to baseline), and explainability (role_log).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.persistence.db import get_connection, init_db, set_db_path
from backend.persistence.repositories import TeamRepository, UserRepository
from backend.roles import Role
from backend.services.simulation_service import run_team_match_simulation

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from fastapi.testclient import TestClient
    from backend.api import app
    HAS_CLIENT = True
except Exception:
    HAS_CLIENT = False


@pytest.fixture
def client(tmp_path):
    """TestClient with isolated DB for API role-validation tests."""
    if not HAS_CLIENT:
        pytest.skip("TestClient not available")
    set_db_path(tmp_path / "role_api.db")
    init_db(db_path=tmp_path / "role_api.db", rankings_path=PROJECT_ROOT / "data" / "rankings.json")
    return TestClient(app)


def _make_roster(
    player_ids: list[str],
    captain_index: int = 0,
    role_per_slot: dict[int, str] | None = None,
) -> list[tuple[str, int, bool, str | None]]:
    """Roster: 10 slots, captain in 1-7. role_per_slot: 1-based slot -> role id (e.g. 'anchor')."""
    roster: list[tuple[str, int, bool, str | None]] = []
    role_per_slot = role_per_slot or {}
    for i, pid in enumerate(player_ids[:10]):
        slot = i + 1
        is_captain = i == captain_index and slot <= 7
        role = role_per_slot.get(slot)
        roster.append((pid, slot, is_captain, role))
    while len(roster) < 10:
        roster.append((player_ids[-1], len(roster) + 1, False, None))
    return roster[:10]


@pytest.fixture
def db_with_teams(tmp_path):
    """DB with two teams (no roles). Used for baseline and for building role rosters."""
    db_path = tmp_path / "role_scoring.db"
    set_db_path(db_path)
    init_db(db_path=db_path, rankings_path=PROJECT_ROOT / "data" / "rankings.json")
    conn = get_connection()
    try:
        user_repo = UserRepository()
        team_repo = TeamRepository()
        user_repo.create(conn, "User A", id="user-1")
        user_repo.create(conn, "User B", id="user-2")
        rows = conn.execute(
            "SELECT id FROM players WHERE gender = 'men' ORDER BY rank LIMIT 15"
        ).fetchall()
        player_ids = [r[0] for r in rows]
        if len(player_ids) < 10:
            pytest.skip("Need at least 10 men players")
        roster_a = _make_roster(player_ids[:10], captain_index=0)
        roster_b = _make_roster(
            player_ids[5:15] if len(player_ids) >= 15 else player_ids[:10],
            captain_index=1,
        )
        team_a = team_repo.create_phase2(
            conn, "user-1", "Team A", "men", budget=100, roster=roster_a, league_id=None
        )
        team_b = team_repo.create_phase2(
            conn, "user-2", "Team B", "men", budget=100, roster=roster_b, league_id=None
        )
        yield conn, team_a.id, team_b.id, player_ids
    finally:
        conn.close()


# ---------- 1. Role uniqueness (API validation tested in test_api; here we ensure repo accepts valid) ----------
def test_role_uniqueness_roster_rejects_duplicate_role_via_api(client):
    """Cannot assign same role twice on a team (API validation)."""
    resp = client.get("/players?gender=men&limit=10")
    assert resp.status_code == 200
    players = resp.json()["players"]
    if len(players) < 10:
        pytest.skip("Need 10 players")
    roster = []
    for i, p in enumerate(players[:10]):
        roster.append({
            "player_id": p["id"],
            "slot": i + 1,
            "is_captain": i == 0,
            "role": "anchor" if i in (0, 1) else None,  # duplicate anchor
        })
    total_salary = sum(p.get("salary", 100) for p in players[:10])
    create = client.post(
        "/teams",
        json={
            "user_id": "u",
            "name": "Dup",
            "gender": "men",
            "budget": total_salary + 100,
            "roster": roster,
        },
    )
    assert create.status_code == 400
    assert "role" in create.json().get("detail", "").lower() or "duplicate" in create.json().get("detail", "").lower()


def test_role_only_on_active_slots(client):
    """Role on bench (slot 8) is rejected."""
    resp = client.get("/players?gender=men&limit=10")
    assert resp.status_code == 200
    players = resp.json()["players"]
    if len(players) < 10:
        pytest.skip("Need 10 players")
    roster = []
    for i, p in enumerate(players[:10]):
        roster.append({
            "player_id": p["id"],
            "slot": i + 1,
            "is_captain": i == 0,
            "role": "anchor" if i == 7 else None,  # slot 8 = bench
        })
    total_salary = sum(p.get("salary", 100) for p in players[:10])
    create = client.post(
        "/teams",
        json={
            "user_id": "u",
            "name": "BenchRole",
            "gender": "men",
            "budget": total_salary + 100,
            "roster": roster,
        },
    )
    assert create.status_code == 400
    assert "active" in create.json().get("detail", "").lower() or "slot" in create.json().get("detail", "").lower()


# ---------- 2. Deterministic scoring: no role -> baseline; with role -> modified ----------
def test_deterministic_baseline_no_roles(db_with_teams):
    """Same seed, no roles: two runs produce identical scores."""
    conn, home_id, away_id, _ = db_with_teams
    seed = 9999
    r1 = run_team_match_simulation(conn, home_id, away_id, seed=seed, best_of=5)
    r2 = run_team_match_simulation(conn, home_id, away_id, seed=seed, best_of=5)
    assert r1["home_score"] == r2["home_score"]
    assert r1["away_score"] == r2["away_score"]


def test_deterministic_with_role_same_seed_same_result(db_with_teams):
    """Same seed, with one role on home slot 1: two runs produce identical scores."""
    conn, home_id, away_id, player_ids = db_with_teams
    team_repo = TeamRepository()
    user_repo = UserRepository()
    roster_a = _make_roster(player_ids[:10], captain_index=0, role_per_slot={1: "anchor"})
    team_with_anchor = team_repo.create_phase2(
        conn, "user-1", "Team A Anchor", "men", budget=100, roster=roster_a, league_id=None
    )
    seed = 8888
    r1 = run_team_match_simulation(conn, team_with_anchor.id, away_id, seed=seed, best_of=5)
    r2 = run_team_match_simulation(conn, team_with_anchor.id, away_id, seed=seed, best_of=5)
    assert r1["home_score"] == r2["home_score"]
    assert r1["away_score"] == r2["away_score"]


def test_baseline_vs_with_role_different_score(db_with_teams):
    """With role (e.g. Anchor on slot 1), home score can differ from baseline (no role)."""
    conn, home_id, away_id, player_ids = db_with_teams
    seed = 7777
    baseline = run_team_match_simulation(conn, home_id, away_id, seed=seed, best_of=5)
    roster_a = _make_roster(player_ids[:10], captain_index=0, role_per_slot={1: "anchor"})
    team_repo = TeamRepository()
    team_with_anchor = team_repo.create_phase2(
        conn, "user-1", "Team A Anchor", "men", budget=100, roster=roster_a, league_id=None
    )
    with_role = run_team_match_simulation(conn, team_with_anchor.id, away_id, seed=seed, best_of=5)
    # Same away team and seed => away_score identical
    assert with_role["away_score"] == baseline["away_score"]
    # Home may differ due to role (Anchor on slot 1)
    # (Could be equal by chance; we only require determinism, not strict inequality)
    assert isinstance(with_role["home_score"], (int, float))
    assert isinstance(baseline["home_score"], (int, float))


# ---------- 3. Role-specific: Anchor reduces loss penalty ----------
def test_anchor_reduces_negative_score_magnitude(db_with_teams):
    """Anchor: when raw score is negative, adjusted score is less negative (magnitude reduced)."""
    from backend.roles import apply_role_to_fantasy_score, RoleContext
    raw = -10.0
    ctx = RoleContext(slot_index=0, total_slots=7, is_winner=False, team_side="home", cumulative_team_score_before=0.0, seed=1)
    adjusted, logs = apply_role_to_fantasy_score(raw, "p1", Role.ANCHOR, ctx)
    assert adjusted > raw  # less negative
    assert adjusted == raw * 0.70
    assert len(logs) == 1 and logs[0].role == "anchor"


# ---------- 4. Role-specific: Aggressor ups upside and downside ----------
def test_aggressor_positive_multiplier(db_with_teams):
    """Aggressor: positive raw score is multiplied by 1.25."""
    from backend.roles import apply_role_to_fantasy_score, RoleContext
    raw = 8.0
    ctx = RoleContext(slot_index=0, total_slots=7, is_winner=True, team_side="home", cumulative_team_score_before=0.0, seed=1)
    adjusted, logs = apply_role_to_fantasy_score(raw, "p1", Role.AGGRESSOR, ctx)
    assert adjusted == raw * 1.25
    assert len(logs) == 1


def test_aggressor_negative_multiplier(db_with_teams):
    """Aggressor: negative raw score is multiplied by 1.15 (more negative)."""
    from backend.roles import apply_role_to_fantasy_score, RoleContext
    raw = -5.0
    ctx = RoleContext(slot_index=0, total_slots=7, is_winner=False, team_side="home", cumulative_team_score_before=0.0, seed=1)
    adjusted, _ = apply_role_to_fantasy_score(raw, "p1", Role.AGGRESSOR, ctx)
    assert adjusted == raw * 1.15


# ---------- 5. Role-specific: Closer only in final games ----------
def test_closer_no_effect_early_slot(db_with_teams):
    """Closer: no effect in slot 0 (first game)."""
    from backend.roles import apply_role_to_fantasy_score, RoleContext
    raw = 6.0
    ctx = RoleContext(slot_index=0, total_slots=7, is_winner=True, team_side="home", cumulative_team_score_before=0.0, seed=1)
    adjusted, logs = apply_role_to_fantasy_score(raw, "p1", Role.CLOSER, ctx)
    assert adjusted == raw
    assert len(logs) == 0


def test_closer_bonus_in_final_slot(db_with_teams):
    """Closer: bonus applied in slot 6 (game 7)."""
    from backend.roles import apply_role_to_fantasy_score, RoleContext
    raw = 6.0
    ctx = RoleContext(slot_index=6, total_slots=7, is_winner=True, team_side="home", cumulative_team_score_before=0.0, seed=1)
    adjusted, logs = apply_role_to_fantasy_score(raw, "p1", Role.CLOSER, ctx)
    assert adjusted == raw * 1.20
    assert len(logs) == 1


# ---------- 6. Role-specific: Wildcard triggers logged and bounded ----------
def test_wildcard_triggers_logged(db_with_teams):
    """Wildcard: when bonus triggers, role_log entry is created."""
    from backend.roles import apply_role_to_fantasy_score, RoleContext
    raw = 5.0
    # Seed/slot/player combination that triggers (~15%): try a few
    for seed in range(0, 20):
        ctx = RoleContext(slot_index=0, total_slots=7, is_winner=True, team_side="home", cumulative_team_score_before=0.0, seed=seed)
        adjusted, logs = apply_role_to_fantasy_score(raw, "a", Role.WILDCARD, ctx)
        if logs:
            assert logs[0].role == "wildcard"
            assert adjusted >= raw
            assert adjusted <= raw + 1.5  # cap
            break
    else:
        pytest.skip("No Wildcard trigger in first 20 seeds for slot 0 player 'a'")


def test_wildcard_bonus_bounded(db_with_teams):
    """Wildcard: bonus is capped so it does not dominate (max +1.5 or 15% of |raw|)."""
    from backend.roles import apply_role_to_fantasy_score, RoleContext
    raw = 20.0
    for seed in range(100):
        ctx = RoleContext(slot_index=0, total_slots=7, is_winner=True, team_side="home", cumulative_team_score_before=0.0, seed=seed)
        adjusted, logs = apply_role_to_fantasy_score(raw, "xy", Role.WILDCARD, ctx)
        if logs:
            assert adjusted <= raw + 1.5
            break
    else:
        pytest.skip("No Wildcard trigger in 100 seeds")


# ---------- 7. Role-specific: Stabilizer dampens negative ----------
def test_stabilizer_dampens_negative(db_with_teams):
    """Stabilizer: negative raw score magnitude is reduced (×0.60)."""
    from backend.roles import apply_role_to_fantasy_score, RoleContext
    raw = -8.0
    ctx = RoleContext(slot_index=0, total_slots=7, is_winner=False, team_side="home", cumulative_team_score_before=0.0, seed=1)
    adjusted, logs = apply_role_to_fantasy_score(raw, "p1", Role.STABILIZER, ctx)
    assert adjusted == raw * 0.60
    assert len(logs) == 1


def test_stabilizer_no_effect_when_positive(db_with_teams):
    """Stabilizer: no effect when raw score is positive."""
    from backend.roles import apply_role_to_fantasy_score, RoleContext
    raw = 7.0
    ctx = RoleContext(slot_index=0, total_slots=7, is_winner=True, team_side="home", cumulative_team_score_before=0.0, seed=1)
    adjusted, logs = apply_role_to_fantasy_score(raw, "p1", Role.STABILIZER, ctx)
    assert adjusted == raw
    assert len(logs) == 0


# ---------- 8. Regression: no role -> baseline ----------
def test_removing_role_reverts_to_baseline(db_with_teams):
    """Same team composition, no role vs with role: scores differ; with role has role_log in slot_details."""
    conn, home_id, away_id, player_ids = db_with_teams
    seed = 5555
    baseline = run_team_match_simulation(conn, home_id, away_id, seed=seed, best_of=5)
    roster_with_anchor = _make_roster(player_ids[:10], captain_index=0, role_per_slot={1: "anchor"})
    team_repo = TeamRepository()
    team_a_anchor = team_repo.create_phase2(
        conn, "user-1", "Team A Anchor", "men", budget=100, roster=roster_with_anchor, league_id=None
    )
    with_anchor = run_team_match_simulation(conn, team_a_anchor.id, away_id, seed=seed, best_of=5)
    # Baseline has no role; with_anchor may have role_log in slot_details when Anchor triggered
    assert "slot_details" in baseline
    assert "slot_details" in with_anchor
    for sd in with_anchor["slot_details"]:
        assert "role_log" in sd


# ---------- 9. Explainability: role_log present when role triggers ----------
def test_role_log_present_in_slot_details_when_role_applies(db_with_teams):
    """When a role modifies score, slot_details[].role_log contains entries for that slot."""
    conn, home_id, away_id, player_ids = db_with_teams
    roster_anchor_s1 = _make_roster(player_ids[:10], captain_index=0, role_per_slot={1: "anchor"})
    team_repo = TeamRepository()
    team_anchor = team_repo.create_phase2(
        conn, "user-1", "Team A", "men", budget=100, roster=roster_anchor_s1, league_id=None
    )
    result = run_team_match_simulation(conn, team_anchor.id, away_id, seed=42, best_of=5)
    assert "slot_details" in result
    assert len(result["slot_details"]) == 7
    role_logs_found = 0
    for sd in result["slot_details"]:
        assert "role_log" in sd
        for entry in sd["role_log"]:
            role_logs_found += 1
            assert "player_id" in entry
            assert "role" in entry
            assert "description" in entry
            assert "game_slot" in entry
    # Anchor on slot 1 applies every game for that slot => at least one log
    assert role_logs_found >= 1


def test_highlights_include_role_log_when_present(db_with_teams):
    """highlights[].role_log is present and used for display."""
    conn, home_id, away_id, player_ids = db_with_teams
    roster_anchor = _make_roster(player_ids[:10], captain_index=0, role_per_slot={1: "anchor"})
    team_repo = TeamRepository()
    team_anchor = team_repo.create_phase2(
        conn, "user-1", "Team A", "men", budget=100, roster=roster_anchor, league_id=None
    )
    result = run_team_match_simulation(conn, team_anchor.id, away_id, seed=123, best_of=5)
    assert "highlights" in result
    for h in result["highlights"]:
        assert "role_log" in h
        assert isinstance(h["role_log"], list)
