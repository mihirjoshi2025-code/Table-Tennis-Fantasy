"""
REST API for the table tennis fantasy backend.
Thin wrappers around domain logic and persistence.
"""
from __future__ import annotations

import json
import random
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Generator

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

# Ensure project root on path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.rankings_db import (
    list_players_by_gender,
    get_player,
    build_profile_store_for_match,
)
from backend.persistence import get_connection, init_db, UserRepository, TeamRepository, MatchRepository
from backend.persistence.db import get_db_path
from backend.scoring import aggregate_stats_from_events, compute_fantasy_score
from backend.simulation.schemas import MatchConfig
from backend.simulation.orchestrator import MatchOrchestrator, sets_to_win_match


# ---------- Project root for data paths ----------
def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _rankings_path() -> Path:
    return _project_root() / "data" / "rankings.json"


@contextmanager
def db_conn() -> Generator:
    """Yield a DB connection, ensure close on exit."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


# ---------- Startup: ensure DB and rankings ----------
def _ensure_db() -> None:
    init_db(db_path=get_db_path(), rankings_path=_rankings_path())


# ---------- Lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    _ensure_db()
    yield


# ---------- FastAPI app ----------
app = FastAPI(
    title="Table Tennis Fantasy API",
    description="Backend for fantasy teams and match simulation",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------- Request/Response models ----------


class CreateTeamRequest(BaseModel):
    user_id: str = Field(..., description="Placeholder user ID")
    name: str = Field(..., min_length=1, max_length=200)
    player_ids: list[str] = Field(..., min_length=1, description="Player IDs (from rankings)")


class SimulateMatchRequest(BaseModel):
    team_a_id: str
    team_b_id: str
    seed: int | None = Field(default=None, description="RNG seed for reproducibility")
    best_of: int = Field(default=5, ge=3, le=5)


# ---------- Endpoints ----------


@app.get("/players")
def get_players(
    gender: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """
    List players from rankings.
    gender: "men" | "women" | omit for all
    """
    with db_conn() as conn:
        if gender:
            if gender not in ("men", "women"):
                raise HTTPException(status_code=400, detail="gender must be 'men' or 'women'")
            rows = list_players_by_gender(conn, gender, limit=limit)
        else:
            men = list_players_by_gender(conn, "men", limit=limit)
            women = list_players_by_gender(conn, "women", limit=limit)
            rows = men + women
        return {
            "players": [
                {
                    "id": r.id,
                    "name": r.name,
                    "country": r.country,
                    "gender": r.gender,
                    "rank": r.rank,
                    "points": r.points,
                }
                for r in rows
            ],
        }


@app.post("/teams")
def create_team(req: CreateTeamRequest) -> dict[str, Any]:
    """
    Create a fantasy team.
    Validates that all player_ids exist in rankings.
    """
    with db_conn() as conn:
        # Validate players exist
        for pid in req.player_ids:
            if get_player(conn, pid) is None:
                raise HTTPException(status_code=400, detail=f"Player not found: {pid}")
        # Ensure user exists (placeholder: create if not)
        user_repo = UserRepository()
        user = user_repo.get(conn, req.user_id)
        if user is None:
            user = user_repo.create(conn, name=f"User {req.user_id[:8]}", id=req.user_id)
        team_repo = TeamRepository()
        team = team_repo.create(conn, req.user_id, req.name, req.player_ids)
        player_ids = team_repo.get_players(conn, team.id)
        return {
            "id": team.id,
            "user_id": team.user_id,
            "name": team.name,
            "player_ids": player_ids,
            "created_at": team.created_at.isoformat(),
        }


@app.get("/teams/{team_id}")
def get_team(team_id: str) -> dict[str, Any]:
    """Get a team by ID with its players."""
    with db_conn() as conn:
        team_repo = TeamRepository()
        team = team_repo.get(conn, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")
        player_ids = team_repo.get_players(conn, team_id)
        # Enrich with player names
        players = []
        for pid in player_ids:
            p = get_player(conn, pid)
            players.append({"id": pid, "name": p.name, "country": p.country} if p else {"id": pid})
        return {
            "id": team.id,
            "user_id": team.user_id,
            "name": team.name,
            "players": players,
            "created_at": team.created_at.isoformat(),
        }


@app.post("/simulate/match")
def simulate_match(req: SimulateMatchRequest) -> dict[str, Any]:
    """
    Simulate a match between two teams, persist the result, and return it.
    Uses the first player from each team (by roster order).
    """
    seed = req.seed if req.seed is not None else random.randint(1, 2**31 - 1)

    with db_conn() as conn:
        team_repo = TeamRepository()
        match_repo = MatchRepository()

        team_a = team_repo.get(conn, req.team_a_id)
        team_b = team_repo.get(conn, req.team_b_id)
        if team_a is None:
            raise HTTPException(status_code=404, detail=f"Team not found: {req.team_a_id}")
        if team_b is None:
            raise HTTPException(status_code=404, detail=f"Team not found: {req.team_b_id}")

        player_ids_a = team_repo.get_players(conn, req.team_a_id)
        player_ids_b = team_repo.get_players(conn, req.team_b_id)
        if not player_ids_a:
            raise HTTPException(status_code=400, detail=f"Team {req.team_a_id} has no players")
        if not player_ids_b:
            raise HTTPException(status_code=400, detail=f"Team {req.team_b_id} has no players")

        player_a_id = player_ids_a[0]
        player_b_id = player_ids_b[0]

        # Build profiles and run simulation (pure domain logic)
        store = build_profile_store_for_match(conn, player_a_id, player_b_id)
        match_id = f"sim-{req.team_a_id[:8]}-{req.team_b_id[:8]}-{seed}"
        config = MatchConfig(
            match_id=match_id,
            player_a_id=player_a_id,
            player_b_id=player_b_id,
            seed=seed,
            best_of=req.best_of,
        )
        orch = MatchOrchestrator(config, store)

        events: list = []
        for ev in orch.run():
            events.append(ev)

        if not events:
            raise HTTPException(status_code=500, detail="Simulation produced no events")

        sets_needed = sets_to_win_match(req.best_of)
        last = events[-1]
        sets_a, sets_b = last.set_scores_after[0], last.set_scores_after[1]
        winner_id = player_a_id if sets_a >= sets_needed else player_b_id

        # Serialize events for optional replay
        def _ev_to_dict(e) -> dict:
            return {
                "match_id": e.match_id,
                "point_index": e.point_index,
                "set_index": e.set_index,
                "score_before": list(e.score_before),
                "score_after": list(e.score_after),
                "set_scores_after": list(e.set_scores_after),
                "outcome": {
                    "winner_id": e.outcome.winner_id,
                    "loser_id": e.outcome.loser_id,
                    "shot_type": e.outcome.shot_type,
                },
                "rally_length": e.rally_length,
                "streak_broken": e.streak_broken,
            }

        events_json = json.dumps([_ev_to_dict(e) for e in events])

        # Persist match
        match = match_repo.create(
            conn,
            team_a_id=req.team_a_id,
            team_b_id=req.team_b_id,
            player_a_id=player_a_id,
            player_b_id=player_b_id,
            winner_id=winner_id,
            sets_a=sets_a,
            sets_b=sets_b,
            best_of=req.best_of,
            seed=seed,
            events_json=events_json,
            id=match_id,
        )

        # Fantasy scores (optional enrichment)
        stats_a, stats_b = aggregate_stats_from_events(
            events, winner_id=winner_id,
            player_a_id=player_a_id, player_b_id=player_b_id,
            best_of=req.best_of,
        )
        fantasy_a = compute_fantasy_score(stats_a)
        fantasy_b = compute_fantasy_score(stats_b)

        return {
            "id": match.id,
            "team_a_id": match.team_a_id,
            "team_b_id": match.team_b_id,
            "player_a_id": match.player_a_id,
            "player_b_id": match.player_b_id,
            "winner_id": match.winner_id,
            "sets_a": match.sets_a,
            "sets_b": match.sets_b,
            "best_of": match.best_of,
            "seed": match.seed,
            "created_at": match.created_at.isoformat(),
            "fantasy_scores": {
                player_a_id: round(fantasy_a, 1),
                player_b_id: round(fantasy_b, 1),
            },
        }


@app.get("/matches/{match_id}")
def get_match(match_id: str) -> dict[str, Any]:
    """Get a match by ID."""
    with db_conn() as conn:
        match_repo = MatchRepository()
        match = match_repo.get(conn, match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="Match not found")
        out: dict[str, Any] = {
            "id": match.id,
            "team_a_id": match.team_a_id,
            "team_b_id": match.team_b_id,
            "player_a_id": match.player_a_id,
            "player_b_id": match.player_b_id,
            "winner_id": match.winner_id,
            "sets_a": match.sets_a,
            "sets_b": match.sets_b,
            "best_of": match.best_of,
            "seed": match.seed,
            "created_at": match.created_at.isoformat(),
        }
        if match.events_json:
            out["events"] = json.loads(match.events_json)
        return out


# ---------- Run with: uvicorn backend.api:app --reload ----------
