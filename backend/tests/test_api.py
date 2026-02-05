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
        json={"user_id": "test-user-1", "name": "Team Alpha", "player_ids": ids},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Team Alpha"
    assert data["user_id"] == "test-user-1"
    assert data["player_ids"] == ids
    assert "id" in data


def test_get_team(client):
    """GET /teams/{id} returns team with player details."""
    resp = client.get("/players?gender=men&limit=3")
    ids = [p["id"] for p in resp.json()["players"][:3]]
    create = client.post("/teams", json={"user_id": "u1", "name": "T1", "player_ids": ids})
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
        json={"user_id": "u1", "name": "T1", "player_ids": ["nonexistent-player-id"]},
    )
    assert resp.status_code == 400


def test_simulate_match(client):
    """POST /simulate/match runs simulation and persists result."""
    resp = client.get("/players?gender=men&limit=5")
    ids = [p["id"] for p in resp.json()["players"][:4]]
    t1 = client.post("/teams", json={"user_id": "u1", "name": "T1", "player_ids": [ids[0], ids[1]]})
    t2 = client.post("/teams", json={"user_id": "u2", "name": "T2", "player_ids": [ids[2], ids[3]]})
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
    """GET /matches/{id} returns persisted match."""
    resp = client.get("/players?gender=women&limit=5")
    ids = [p["id"] for p in resp.json()["players"][:4]]
    t1 = client.post("/teams", json={"user_id": "u1", "name": "T1", "player_ids": [ids[0], ids[1]]})
    t2 = client.post("/teams", json={"user_id": "u2", "name": "T2", "player_ids": [ids[2], ids[3]]})
    sim = client.post("/simulate/match", json={"team_a_id": t1.json()["id"], "team_b_id": t2.json()["id"], "seed": 99})
    mid = sim.json()["id"]
    resp = client.get(f"/matches/{mid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == mid
    assert "events" in data
    assert len(data["events"]) > 0


def test_vertical_slice(client):
    """
    Full vertical slice:
    1. Create two teams
    2. Simulate match between them
    3. Persist result (automatic)
    4. Retrieve match data
    """
    resp = client.get("/players?gender=men&limit=10")
    players = resp.json()["players"]
    ids = [p["id"] for p in players[:6]]
    team_a = client.post("/teams", json={"user_id": "slice-user", "name": "Champions", "player_ids": ids[:3]})
    team_b = client.post("/teams", json={"user_id": "slice-user", "name": "Underdogs", "player_ids": ids[3:6]})
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
    """GET /analysis/match/{id} returns deterministic analytics."""
    resp = client.get("/players?gender=men&limit=4")
    ids = [p["id"] for p in resp.json()["players"][:4]]
    t1 = client.post("/teams", json={"user_id": "u1", "name": "T1", "player_ids": [ids[0], ids[1]]})
    t2 = client.post("/teams", json={"user_id": "u2", "name": "T2", "player_ids": [ids[2], ids[3]]})
    sim = client.post("/simulate/match", json={"team_a_id": t1.json()["id"], "team_b_id": t2.json()["id"], "seed": 77})
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
    t1 = client.post("/teams", json={"user_id": "u1", "name": "T1", "player_ids": [ids[0], ids[1]]})
    t2 = client.post("/teams", json={"user_id": "u2", "name": "T2", "player_ids": [ids[2], ids[3]]})
    sim = client.post("/simulate/match", json={"team_a_id": t1.json()["id"], "team_b_id": t2.json()["id"], "seed": 1})
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
    t1 = client.post("/teams", json={"user_id": "u1", "name": "T1", "player_ids": [ids[0], ids[1]]})
    t2 = client.post("/teams", json={"user_id": "u2", "name": "T2", "player_ids": [ids[2], ids[3]]})
    sim = client.post("/simulate/match", json={"team_a_id": t1.json()["id"], "team_b_id": t2.json()["id"], "seed": 88})
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
