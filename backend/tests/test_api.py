"""
API integration tests.
Uses TestClient to avoid starting a server.
Requires: pip install httpx (for TestClient)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from fastapi.testclient import TestClient
    HAS_HTTPX = True
except (ImportError, RuntimeError):
    HAS_HTTPX = False

# Ensure project root on path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

pytestmark = pytest.mark.skipif(not HAS_HTTPX, reason="httpx required for TestClient")

from backend.api import app
from backend.persistence.db import set_db_path, init_db

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Use a temporary DB for each test."""
    db_path = tmp_path / "test.db"
    set_db_path(db_path)
    init_db(db_path=db_path, rankings_path=PROJECT_ROOT / "data" / "rankings.json")
    yield db_path


@pytest.fixture
def client():
    return TestClient(app)


def test_get_players(client):
    """GET /players returns list of players."""
    resp = client.get("/players")
    assert resp.status_code == 200
    data = resp.json()
    assert "players" in data
    assert len(data["players"]) > 0
    p = data["players"][0]
    assert "id" in p
    assert "name" in p
    assert "country" in p
    assert "gender" in p
    assert "rank" in p
    assert "points" in p


def test_get_players_filter_gender(client):
    """GET /players?gender=men filters correctly."""
    resp = client.get("/players?gender=men")
    assert resp.status_code == 200
    data = resp.json()
    assert all(p["gender"] == "men" for p in data["players"])


def test_post_teams(client):
    """POST /teams creates a team with players."""
    resp = client.get("/players?gender=men&limit=5")
    players = resp.json()["players"]
    ids = [p["id"] for p in players[:3]]
    resp = client.post(
        "/teams",
        json={"user_id": "test-user-1", "name": "Team Alpha", "gender": "men", "player_ids": ids},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Team Alpha"
    assert data["user_id"] == "test-user-1"
    assert data["gender"] == "men"
    assert data["player_ids"] == ids
    assert "id" in data


def test_get_team(client):
    """GET /teams/{id} returns team with player details."""
    resp = client.get("/players?gender=men&limit=3")
    ids = [p["id"] for p in resp.json()["players"][:3]]
    create = client.post("/teams", json={"user_id": "u1", "name": "T1", "gender": "men", "player_ids": ids})
    tid = create.json()["id"]
    resp = client.get(f"/teams/{tid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == tid
    assert data["name"] == "T1"
    assert len(data["players"]) == 3
    assert all("name" in p for p in data["players"])


def test_post_teams_invalid_player(client):
    """POST /teams with unknown player returns 400."""
    resp = client.post(
        "/teams",
        json={"user_id": "u1", "name": "T1", "gender": "men", "player_ids": ["nonexistent-player-id"]},
    )
    assert resp.status_code == 400


def test_simulate_match(client):
    """POST /simulate/match runs simulation and persists result (Phase 2: manual trigger)."""
    resp = client.get("/players?gender=men&limit=5")
    ids = [p["id"] for p in resp.json()["players"][:4]]
    t1 = client.post("/teams", json={"user_id": "u1", "name": "T1", "gender": "men", "player_ids": [ids[0], ids[1]]})
    t2 = client.post("/teams", json={"user_id": "u2", "name": "T2", "gender": "men", "player_ids": [ids[2], ids[3]]})
    tid1, tid2 = t1.json()["id"], t2.json()["id"]
    resp = client.post(
        "/simulate/match",
        json={"team_a_id": tid1, "team_b_id": tid2, "seed": 42, "best_of": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["team_a_id"] == tid1
    assert data["team_b_id"] == tid2
    assert data["winner_id"] in (ids[0], ids[2])
    assert data["sets_a"] + data["sets_b"] >= 3
    assert "fantasy_scores" in data


def test_get_match(client):
    """GET /matches/{id} returns persisted match (created via simulate)."""
    resp = client.get("/players?gender=women&limit=4")
    ids = [p["id"] for p in resp.json()["players"][:4]]
    t1 = client.post("/teams", json={"user_id": "u1", "name": "T1", "gender": "women", "player_ids": ids[:2]})
    t2 = client.post("/teams", json={"user_id": "u2", "name": "T2", "gender": "women", "player_ids": ids[2:4]})
    sim = client.post("/simulate/match", json={"team_a_id": t1.json()["id"], "team_b_id": t2.json()["id"], "seed": 99})
    assert sim.status_code == 200
    mid = sim.json()["id"]
    resp = client.get(f"/matches/{mid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == mid
    assert "events" in data
    assert len(data["events"]) > 0


def test_vertical_slice(client):
    """
    Full vertical slice: create two teams, simulate match, persist, retrieve match.
    """
    resp = client.get("/players?gender=men&limit=6")
    players = resp.json()["players"]
    ids = [p["id"] for p in players[:6]]
    team_a = client.post("/teams", json={"user_id": "slice-user", "name": "Champions", "gender": "men", "player_ids": ids[:3]})
    team_b = client.post("/teams", json={"user_id": "slice-user", "name": "Underdogs", "gender": "men", "player_ids": ids[3:6]})
    assert team_a.status_code == 200
    assert team_b.status_code == 200
    aid, bid = team_a.json()["id"], team_b.json()["id"]
    sim = client.post("/simulate/match", json={"team_a_id": aid, "team_b_id": bid, "seed": 12345})
    assert sim.status_code == 200
    match = sim.json()
    mid = match["id"]
    resp = client.get(f"/matches/{mid}")
    assert resp.status_code == 200
    retrieved = resp.json()
    assert retrieved["id"] == mid
    assert retrieved["winner_id"] == match["winner_id"]
    assert retrieved["sets_a"] == match["sets_a"]
    assert retrieved["sets_b"] == match["sets_b"]
    assert len(retrieved["events"]) > 0


def test_get_analysis_match(client):
    """GET /analysis/match/{id} returns deterministic analytics (match from simulate)."""
    resp = client.get("/players?gender=men&limit=4")
    ids = [p["id"] for p in resp.json()["players"][:4]]
    t1 = client.post("/teams", json={"user_id": "u1", "name": "T1", "gender": "men", "player_ids": [ids[0], ids[1]]})
    t2 = client.post("/teams", json={"user_id": "u2", "name": "T2", "gender": "men", "player_ids": [ids[2], ids[3]]})
    sim = client.post("/simulate/match", json={"team_a_id": t1.json()["id"], "team_b_id": t2.json()["id"], "seed": 77})
    assert sim.status_code == 200
    mid = sim.json()["id"]
    resp = client.get(f"/analysis/match/{mid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["match_id"] == mid
    assert "outcome" in data
    assert data["outcome"]["winner_id"] in (ids[0], ids[2])
    assert "player_a_stats" in data
    assert "player_b_stats" in data
    assert "fantasy_scores" in data


def test_get_analysis_match_not_found(client):
    """GET /analysis/match/{id} returns 404 for unknown match."""
    resp = client.get("/analysis/match/nonexistent-match-id")
    assert resp.status_code == 404


def test_explain_match_not_found(client):
    """POST /explain/match returns 404 when match does not exist."""
    resp = client.post("/explain/match", json={"match_id": "nonexistent-match-id"})
    assert resp.status_code == 404


def test_explain_match_stub_when_no_api_key(client):
    """POST /explain/match returns 200 with stub response when OPENAI_API_KEY is not set."""
    resp = client.get("/players?gender=men&limit=4")
    ids = [p["id"] for p in resp.json()["players"][:4]]
    t1 = client.post("/teams", json={"user_id": "u1", "name": "T1", "gender": "men", "player_ids": [ids[0], ids[1]]})
    t2 = client.post("/teams", json={"user_id": "u2", "name": "T2", "gender": "men", "player_ids": [ids[2], ids[3]]})
    sim = client.post("/simulate/match", json={"team_a_id": t1.json()["id"], "team_b_id": t2.json()["id"], "seed": 1})
    assert sim.status_code == 200
    mid = sim.json()["id"]
    with patch.dict("os.environ", {}, clear=True):
        resp = client.post("/explain/match", json={"match_id": mid})
    assert resp.status_code == 200
    data = resp.json()
    assert "explanation_text" in data
    assert "supporting_facts" in data
    assert "OPENAI_API_KEY" in data["explanation_text"] or "Stub" in str(data.get("supporting_facts", []))


def test_explain_match_success(client):
    """POST /explain/match returns explanation_text and supporting_facts when LLM is mocked."""
    resp = client.get("/players?gender=men&limit=4")
    ids = [p["id"] for p in resp.json()["players"][:4]]
    t1 = client.post("/teams", json={"user_id": "u1", "name": "T1", "gender": "men", "player_ids": [ids[0], ids[1]]})
    t2 = client.post("/teams", json={"user_id": "u2", "name": "T2", "gender": "men", "player_ids": [ids[2], ids[3]]})
    sim = client.post("/simulate/match", json={"team_a_id": t1.json()["id"], "team_b_id": t2.json()["id"], "seed": 88})
    assert sim.status_code == 200
    mid = sim.json()["id"]
    from backend.explanation import ExplainResponse
    with patch("backend.api.explain_match") as mock_explain:
        mock_explain.return_value = ExplainResponse(
            explanation_text="Team A won in 3 sets due to stronger service and fewer unforced errors.",
            supporting_facts=["Winner won 3 sets.", "Net point differential favored winner."],
        )
        resp = client.post("/explain/match", json={"match_id": mid, "user_query": "Why did the winner win?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "explanation_text" in data
    assert "supporting_facts" in data
    assert isinstance(data["supporting_facts"], list)
    assert len(data["explanation_text"]) > 0


# ---------- Phase 2: Auth, team constraints, team match simulation ----------


def test_signup_and_login(client):
    """POST /signup and POST /login return user_id, username, token."""
    signup = client.post("/signup", json={"username": "phase2user", "password": "secret123"})
    assert signup.status_code == 200
    data = signup.json()
    assert "user_id" in data
    assert data["username"] == "phase2user"
    assert "token" in data
    assert len(data["token"]) > 0

    login = client.post("/login", json={"username": "phase2user", "password": "secret123"})
    assert login.status_code == 200
    data2 = login.json()
    assert data2["user_id"] == data["user_id"]
    assert data2["username"] == "phase2user"
    assert "token" in data2


def test_login_wrong_password(client):
    """POST /login with wrong password returns 401."""
    client.post("/signup", json={"username": "u2", "password": "correct123"})
    resp = client.post("/login", json={"username": "u2", "password": "wrong"})
    assert resp.status_code == 401


def test_post_teams_phase2_roster_budget(client):
    """POST /teams with roster and budget creates Phase 2 team (7 active, 3 bench, one captain)."""
    resp = client.get("/players?gender=men&limit=15")
    assert resp.status_code == 200
    players = resp.json()["players"]
    assert len(players) >= 10
    total_salary = 0
    roster = []
    for i, p in enumerate(players[:10]):
        slot = i + 1
        salary = p.get("salary", 100)
        total_salary += salary
        roster.append({"player_id": p["id"], "slot": slot, "is_captain": slot == 1})
    budget = total_salary + 100
    create = client.post(
        "/teams",
        json={
            "name": "Phase2 Team",
            "gender": "men",
            "budget": budget,
            "roster": roster,
        },
    )
    assert create.status_code in (400, 401), "Expected 400/401 when no auth: need token or user_id for roster"
    # With user_id in body (no token) it should work for testing
    create2 = client.post(
        "/teams",
        json={
            "user_id": "test-user-phase2",
            "name": "Phase2 Team",
            "gender": "men",
            "budget": budget,
            "roster": roster,
        },
    )
    assert create2.status_code == 200, create2.text
    data = create2.json()
    assert data["name"] == "Phase2 Team"
    assert data.get("budget") == budget
    assert "roster" in data
    assert len(data["roster"]) == 10
    slots = [r["slot"] for r in data["roster"]]
    assert set(slots) == set(range(1, 11))
    captains = [r for r in data["roster"] if r.get("is_captain")]
    assert len(captains) == 1
    assert captains[0]["slot"] == 1


def test_post_teams_phase2_budget_exceeded(client):
    """POST /teams with roster total salary > budget returns 400."""
    resp = client.get("/players?gender=women&limit=10")
    players = resp.json()["players"]
    roster = []
    total = 0
    for i, p in enumerate(players[:10]):
        roster.append({"player_id": p["id"], "slot": i + 1, "is_captain": i == 0})
        total += p.get("salary", 100)
    budget = max(0, total - 50)
    create = client.post(
        "/teams",
        json={
            "user_id": "u",
            "name": "Over",
            "gender": "women",
            "budget": budget,
            "roster": roster,
        },
    )
    assert create.status_code == 400
    assert "salary" in create.json().get("detail", "").lower() or "budget" in create.json().get("detail", "").lower()


def test_post_teams_phase2_captain_must_be_active(client):
    """POST /teams with captain in slot 8 (bench) returns 400."""
    resp = client.get("/players?gender=men&limit=10")
    players = resp.json()["players"]
    roster = []
    total = 0
    for i, p in enumerate(players[:10]):
        roster.append({"player_id": p["id"], "slot": i + 1, "is_captain": i == 7})
        total += p.get("salary", 100)
    create = client.post(
        "/teams",
        json={
            "user_id": "u",
            "name": "BadCaptain",
            "gender": "men",
            "budget": total + 100,
            "roster": roster,
        },
    )
    assert create.status_code == 400
    assert "captain" in create.json().get("detail", "").lower()


def test_simulate_team_match(client):
    """POST /simulate/team-match runs 7v7, returns score_a, score_b, highlights; captain bonus applied (Phase 2)."""
    resp = client.get("/players?gender=men&limit=15")
    players = resp.json()["players"]
    assert len(players) >= 10
    total_salary = sum(p.get("salary", 100) for p in players[:10])
    roster_a = [
        {"player_id": players[i]["id"], "slot": i + 1, "is_captain": i == 0}
        for i in range(10)
    ]
    roster_b = [
        {"player_id": players[i + 5]["id"], "slot": i + 1, "is_captain": i == 1}
        for i in range(10)
    ]
    if len(players) < 15:
        roster_b = [{"player_id": p["id"], "slot": i + 1, "is_captain": i == 1} for i, p in enumerate(players[:10])]
    budget = total_salary + 200
    t1 = client.post(
        "/teams",
        json={"user_id": "ua", "name": "Team A", "gender": "men", "budget": budget, "roster": roster_a},
    )
    t2 = client.post(
        "/teams",
        json={"user_id": "ub", "name": "Team B", "gender": "men", "budget": budget, "roster": roster_b},
    )
    assert t1.status_code == 200
    assert t2.status_code == 200
    tid_a, tid_b = t1.json()["id"], t2.json()["id"]
    sim = client.post(
        "/simulate/team-match",
        json={"team_a_id": tid_a, "team_b_id": tid_b, "seed": 999, "best_of": 5},
    )
    assert sim.status_code == 200, sim.text
    data = sim.json()
    assert "score_a" in data
    assert "score_b" in data
    assert "captain_a_id" in data
    assert "captain_b_id" in data
    assert "match_ids" in data
    assert "highlights" in data
    assert len(data["match_ids"]) == 7
    assert len(data["highlights"]) == 7
    sum_a = sum(h["points_a"] for h in data["highlights"])
    sum_b = sum(h["points_b"] for h in data["highlights"])
    assert abs(data["score_a"] - sum_a) < 0.2
    assert abs(data["score_b"] - sum_b) < 0.2
    assert data["captain_a_id"] == roster_a[0]["player_id"]
    assert data["captain_b_id"] == roster_b[1]["player_id"]
    for h in data["highlights"]:
        assert 1 <= h["slot"] <= 7


def test_simulate_team_match_cross_gender_rejected(client):
    """POST /simulate/team-match with men vs women returns 400."""
    resp = client.get("/players?gender=men&limit=10")
    men = resp.json()["players"]
    resp2 = client.get("/players?gender=women&limit=10")
    women = resp2.json()["players"]
    assert len(men) >= 10 and len(women) >= 10
    total_m = sum(p.get("salary", 100) for p in men[:10])
    total_w = sum(p.get("salary", 100) for p in women[:10])
    roster_m = [{"player_id": men[i]["id"], "slot": i + 1, "is_captain": i == 0} for i in range(10)]
    roster_w = [{"player_id": women[i]["id"], "slot": i + 1, "is_captain": i == 0} for i in range(10)]
    t_men = client.post(
        "/teams",
        json={"user_id": "u1", "name": "Men Team", "gender": "men", "budget": total_m + 100, "roster": roster_m},
    )
    t_women = client.post(
        "/teams",
        json={"user_id": "u2", "name": "Women Team", "gender": "women", "budget": total_w + 100, "roster": roster_w},
    )
    assert t_men.status_code == 200
    assert t_women.status_code == 200
    sim = client.post(
        "/simulate/team-match",
        json={"team_a_id": t_men.json()["id"], "team_b_id": t_women.json()["id"]},
    )
    assert sim.status_code == 400
    assert "gender" in sim.json().get("detail", "").lower()


def test_explain_match_from_team_match(client):
    """After simulating a team match, Explain Match works with one of the returned match_ids."""
    resp = client.get("/players?gender=men&limit=10")
    players = resp.json()["players"]
    roster = [
        {"player_id": players[i]["id"], "slot": i + 1, "is_captain": i == 0}
        for i in range(10)
    ]
    budget = sum(p.get("salary", 100) for p in players[:10]) + 100
    t1 = client.post(
        "/teams",
        json={"user_id": "u1", "name": "TA", "gender": "men", "budget": budget, "roster": roster},
    )
    t2 = client.post(
        "/teams",
        json={"user_id": "u2", "name": "TB", "gender": "men", "budget": budget, "roster": roster},
    )
    assert t1.status_code == 200
    assert t2.status_code == 200
    sim = client.post(
        "/simulate/team-match",
        json={"team_a_id": t1.json()["id"], "team_b_id": t2.json()["id"], "seed": 111},
    )
    assert sim.status_code == 200
    match_ids = sim.json()["match_ids"]
    assert len(match_ids) == 7
    with patch("backend.api.explain_match") as mock_explain:
        from backend.explanation import ExplainResponse
        mock_explain.return_value = ExplainResponse(
            explanation_text="Team match was decided by captain performance.",
            supporting_facts=["Captain bonus applied."],
        )
        resp = client.post("/explain/match", json={"match_id": match_ids[0]})
    assert resp.status_code == 200
    data = resp.json()
    assert "explanation_text" in data
    assert "supporting_facts" in data


def test_advise_roles_returns_200(client):
    """POST /advise/roles returns 200 with recommendations and explanation (stub when no API key)."""
    resp = client.post(
        "/advise/roles",
        json={"query": "Who should I assign as my Aggressor?", "gender": "men"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "recommendations" in data
    assert "explanation" in data
    assert isinstance(data["recommendations"], list)


def test_advise_roles_team_not_found(client):
    """POST /advise/roles with invalid team_id returns 404."""
    resp = client.post(
        "/advise/roles",
        json={"query": "Who should be Anchor?", "team_id": "nonexistent-team-id"},
    )
    assert resp.status_code == 404
    assert "team" in resp.json().get("detail", "").lower()
