"""
REST API for the table tennis fantasy backend.
Thin wrappers around domain logic and persistence.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Generator

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

# Ensure project root on path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.auth import create_access_token, decode_token, hash_password, verify_password

_MAX_PASSWORD_BYTES = 72


def _truncate_password(s: str) -> str:
    """Ensure password is at most 72 UTF-8 bytes for bcrypt compatibility."""
    b = s.encode("utf-8")
    if len(b) <= _MAX_PASSWORD_BYTES:
        return s
    return b[:_MAX_PASSWORD_BYTES].decode("utf-8", errors="replace")
from backend.rankings_db import list_players_by_gender, get_player
from backend.persistence import (
    get_connection,
    init_db,
    UserRepository,
    TeamRepository,
    MatchRepository,
    TeamMatchRepository,
)
from backend.analytics import compute_match_analytics as compute_match_analytics_fn
from backend.explanation import ExplainResponse, explain_match
from backend.persistence.db import get_db_path
from backend.scoring import aggregate_stats_from_events, compute_fantasy_score
from backend.services.simulation_service import run_team_match_simulation
from backend.simulation.persistence import event_to_dict
from backend.simulation.schemas import MatchConfig
from backend.simulation.orchestrator import MatchOrchestrator, sets_to_win_match
from backend.rankings_db import build_profile_store_for_match


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://0.0.0.0:5173",
        "http://[::1]:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ---------- Request/Response models ----------


# Team size limits for validation
TEAM_MIN_PLAYERS = 1
TEAM_MAX_PLAYERS = 10
# Phase 2
TEAM_ACTIVE = 7
TEAM_BENCH = 3
TEAM_TOTAL = 10
CAPTAIN_BONUS_MULTIPLIER = 1.5

security = HTTPBearer(auto_error=False)


class SignupRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6)


class LoginRequest(BaseModel):
    username: str
    password: str


class RosterSlot(BaseModel):
    player_id: str
    slot: int = Field(..., ge=1, le=10)
    is_captain: bool = False


class CreateTeamRequest(BaseModel):
    user_id: str | None = Field(None, description="Phase 1: placeholder; Phase 2 use auth")
    name: str = Field(..., min_length=1, max_length=200)
    gender: str = Field(..., description="Team gender: 'men' or 'women'")
    player_ids: list[str] | None = Field(None, description="Phase 1: player IDs")
    budget: int | None = Field(None, description="Phase 2: max total salary")
    roster: list[RosterSlot] | None = Field(None, description="Phase 2: 10 players, slot 1-7 active 8-10 bench, one captain in 1-7")


class SimulateMatchRequest(BaseModel):
    team_a_id: str
    team_b_id: str
    seed: int | None = Field(default=None, description="RNG seed for reproducibility")
    best_of: int = Field(default=5, ge=3, le=5)


class ExplainMatchRequest(BaseModel):
    match_id: str = Field(..., description="Match ID to explain")
    user_query: str | None = Field(default=None, description="Optional question, e.g. 'Why did Team A lose?'")


class SimulateTeamMatchRequest(BaseModel):
    team_a_id: str
    team_b_id: str
    seed: int | None = None
    best_of: int = Field(default=5, ge=3, le=5)


def _get_current_user_id(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> str | None:
    """Phase 2: return user_id from JWT or None if no/invalid token."""
    if credentials is None:
        return None
    return decode_token(credentials.credentials)


# ---------- Endpoints ----------


@app.post("/signup")
def signup(req: SignupRequest) -> dict[str, Any]:
    """Phase 2: create account. Passwords hashed, never stored plain."""
    with db_conn() as conn:
        user_repo = UserRepository()
        if user_repo.get_by_username(conn, req.username):
            raise HTTPException(status_code=400, detail="Username already taken")
        user = user_repo.create_with_password(
            conn, req.username, hash_password(_truncate_password(req.password)), name=req.username
        )
        token = create_access_token(user.id)
        return {"user_id": user.id, "username": user.username, "token": token}


@app.post("/login")
def login(req: LoginRequest) -> dict[str, Any]:
    """Phase 2: login. Returns JWT token."""
    with db_conn() as conn:
        user_repo = UserRepository()
        user = user_repo.get_by_username(conn, req.username)
        if user is None or not user.password_hash or not verify_password(_truncate_password(req.password), user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token = create_access_token(user.id)
        return {"user_id": user.id, "username": user.username, "token": token}


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
                    "salary": getattr(r, "salary", 100),
                }
                for r in rows
            ],
        }


@app.post("/teams")
def create_team(
    req: CreateTeamRequest,
    user_id_from_token: str | None = Depends(_get_current_user_id),
) -> dict[str, Any]:
    """
    Create a fantasy team.
    Phase 1: user_id in body, player_ids. Phase 2: auth + budget + roster (10 players, captain, active/bench).
    """
    if req.gender not in ("men", "women"):
        raise HTTPException(status_code=400, detail="gender must be 'men' or 'women'")

    with db_conn() as conn:
        user_repo = UserRepository()
        team_repo = TeamRepository()

        # Phase 2: roster + budget
        if req.roster is not None:
            if req.budget is None:
                raise HTTPException(status_code=400, detail="budget required when using roster")
            uid = user_id_from_token or req.user_id
            if not uid:
                raise HTTPException(status_code=401, detail="Login required to create team (Phase 2)")
            if len(req.roster) != TEAM_TOTAL:
                raise HTTPException(
                    status_code=400,
                    detail=f"Roster must have exactly {TEAM_TOTAL} players (7 active, 3 bench)",
                )
            slots = [r.slot for r in req.roster]
            if set(slots) != set(range(1, TEAM_TOTAL + 1)):
                raise HTTPException(status_code=400, detail="Slots must be 1-10 exactly once")
            captains = [r for r in req.roster if r.is_captain]
            if len(captains) != 1:
                raise HTTPException(status_code=400, detail="Exactly one captain required")
            if captains[0].slot > TEAM_ACTIVE:
                raise HTTPException(status_code=400, detail="Captain must be in active slots (1-7)")
            total_salary = 0
            for r in req.roster:
                p = get_player(conn, r.player_id)
                if p is None:
                    raise HTTPException(status_code=400, detail=f"Player not found: {r.player_id}")
                if p.gender != req.gender:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Player {r.player_id} has gender '{p.gender}'; team gender is '{req.gender}'",
                    )
                total_salary += getattr(p, "salary", 100)
            if total_salary > req.budget:
                raise HTTPException(
                    status_code=400,
                    detail=f"Total salary {total_salary} exceeds budget {req.budget}",
                )
            roster_tuples = [(r.player_id, r.slot, r.is_captain) for r in req.roster]
            team = team_repo.create_phase2(conn, uid, req.name, req.gender, req.budget, roster_tuples)
            with_slots = team_repo.get_players_with_slots(conn, team.id)
            return {
                "id": team.id,
                "user_id": team.user_id,
                "name": team.name,
                "gender": team.gender,
                "budget": team.budget,
                "roster": [{"player_id": p, "slot": s, "is_captain": c} for p, s, c in with_slots],
                "created_at": team.created_at.isoformat(),
            }

        # Phase 1: player_ids
        player_ids = req.player_ids or []
        if not (TEAM_MIN_PLAYERS <= len(player_ids) <= TEAM_MAX_PLAYERS):
            raise HTTPException(
                status_code=400,
                detail=f"Team must have between {TEAM_MIN_PLAYERS} and {TEAM_MAX_PLAYERS} players",
            )
        for pid in player_ids:
            p = get_player(conn, pid)
            if p is None:
                raise HTTPException(status_code=400, detail=f"Player not found: {pid}")
            if p.gender != req.gender:
                raise HTTPException(
                    status_code=400,
                    detail=f"Player {pid} has gender '{p.gender}'; team gender is '{req.gender}'",
                )
        uid = req.user_id or user_id_from_token
        if not uid:
            raise HTTPException(status_code=400, detail="user_id required when not using auth")
        user = user_repo.get(conn, uid)
        if user is None:
            user = user_repo.create(conn, name=f"User {uid[:8]}", id=uid)
        team = team_repo.create(conn, uid, req.name, req.gender, player_ids)
        player_ids_out = team_repo.get_players(conn, team.id)
        return {
            "id": team.id,
            "user_id": team.user_id,
            "name": team.name,
            "gender": team.gender,
            "player_ids": player_ids_out,
            "created_at": team.created_at.isoformat(),
        }


@app.get("/teams")
def list_teams(
    user_id: str | None = Query(None, description="Filter by owner (Phase 2: list user's teams)"),
    gender: str | None = Query(None, description="Filter by gender: 'men' or 'women' (no cross-gender)"),
) -> dict[str, Any]:
    """List teams; if user_id provided, return only that user's teams. Optional gender filter."""
    with db_conn() as conn:
        team_repo = TeamRepository()
        if user_id:
            teams = team_repo.list_by_user(conn, user_id)
        else:
            teams = []
        if gender and gender in ("men", "women"):
            teams = [t for t in teams if t.gender == gender]
        return {
            "teams": [
                {
                    "id": t.id,
                    "user_id": t.user_id,
                    "name": t.name,
                    "gender": t.gender,
                    "budget": t.budget,
                    "created_at": t.created_at.isoformat(),
                }
                for t in teams
            ],
        }


def _last_match_points_for_player(
    conn, match_repo: MatchRepository, player_id: str
) -> float | None:
    """Return fantasy points from this player's most recent match, or None if none/no events."""
    match = match_repo.get_most_recent_for_player(conn, player_id)
    if match is None or not match.events_json:
        return None
    events = json.loads(match.events_json)
    stats_a, stats_b = aggregate_stats_from_events(
        events,
        winner_id=match.winner_id,
        player_a_id=match.player_a_id,
        player_b_id=match.player_b_id,
        best_of=match.best_of,
    )
    if player_id == match.player_a_id:
        return round(compute_fantasy_score(stats_a), 1)
    return round(compute_fantasy_score(stats_b), 1)


@app.get("/teams/{team_id}")
def get_team(team_id: str) -> dict[str, Any]:
    """Get a team by ID with its players and roster (with last_match_points per player)."""
    with db_conn() as conn:
        team_repo = TeamRepository()
        match_repo = MatchRepository()
        team = team_repo.get(conn, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")
        player_ids = team_repo.get_players(conn, team_id)
        # Enrich with player names
        players = []
        for pid in player_ids:
            p = get_player(conn, pid)
            players.append({"id": pid, "name": p.name, "country": p.country} if p else {"id": pid})
        out = {
            "id": team.id,
            "user_id": team.user_id,
            "name": team.name,
            "gender": team.gender,
            "players": players,
            "created_at": team.created_at.isoformat(),
        }
        if team.budget is not None:
            out["budget"] = team.budget
        with_slots = team_repo.get_players_with_slots(conn, team_id)
        if with_slots and len(with_slots[0]) >= 2:
            out["roster"] = [
                {
                    "player_id": p,
                    "slot": s,
                    "is_captain": c,
                    "last_match_points": _last_match_points_for_player(conn, match_repo, p),
                }
                for p, s, c in with_slots
            ]
        return out


@app.post("/simulate/team-match")
def simulate_team_match(req: SimulateTeamMatchRequest) -> dict[str, Any]:
    """
    Phase 2: Simulate team vs team. 7 active players each, captain +50% points.
    Bench players do not score. Persists individual matches and aggregate team match; returns scores and highlights.
    """
    import random
    seed_base = req.seed if req.seed is not None else random.randint(1, 2**31 - 1)
    with db_conn() as conn:
        team_repo = TeamRepository()
        match_repo = MatchRepository()
        team_match_repo = TeamMatchRepository()
        team_a = team_repo.get(conn, req.team_a_id)
        team_b = team_repo.get(conn, req.team_b_id)
        if team_a is None:
            raise HTTPException(status_code=404, detail=f"Team not found: {req.team_a_id}")
        if team_b is None:
            raise HTTPException(status_code=404, detail=f"Team not found: {req.team_b_id}")
        if team_a.gender != team_b.gender:
            raise HTTPException(
                status_code=400,
                detail="Teams must be the same gender (men vs men or women vs women).",
            )
        active_a = team_repo.get_active_player_ids(conn, req.team_a_id)
        active_b = team_repo.get_active_player_ids(conn, req.team_b_id)
        if len(active_a) != TEAM_ACTIVE:
            raise HTTPException(
                status_code=400,
                detail=f"Team A must have exactly {TEAM_ACTIVE} active players (slots 1-7)",
            )
        if len(active_b) != TEAM_ACTIVE:
            raise HTTPException(
                status_code=400,
                detail=f"Team B must have exactly {TEAM_ACTIVE} active players (slots 1-7)",
            )
        captain_a = team_repo.get_captain_id(conn, req.team_a_id)
        captain_b = team_repo.get_captain_id(conn, req.team_b_id)

        result = run_team_match_simulation(
            conn, req.team_a_id, req.team_b_id, seed=seed_base, best_of=req.best_of
        )
        score_a = result["home_score"]
        score_b = result["away_score"]
        slot_details = result["slot_details"]
        highlights_raw = result["highlights"]

        for slot in slot_details:
            match_repo.create(
                conn,
                req.team_a_id,
                req.team_b_id,
                slot["player_a_id"],
                slot["player_b_id"],
                slot["winner_id"],
                slot["sets_a"],
                slot["sets_b"],
                req.best_of,
                slot["seed"],
                events_json=slot["events_json"],
                id=slot["match_id"],
            )

        tm_id = f"tm-{req.team_a_id[:8]}-{req.team_b_id[:8]}-{seed_base}"
        tm = team_match_repo.create(
            conn, req.team_a_id, req.team_b_id,
            score_a, score_b, captain_a, captain_b, id=tm_id,
        )

        match_ids = [s["match_id"] for s in slot_details]
        highlights = [
            {
                "slot": h["slot"],
                "player_a_id": h["home_player_id"],
                "player_b_id": h["away_player_id"],
                "player_a_name": h["home_player_name"],
                "player_b_name": h["away_player_name"],
                "points_a": h["points_home"],
                "points_b": h["points_away"],
                "winner_id": h["winner_id"],
                "match_id": slot_details[i]["match_id"],
            }
            for i, h in enumerate(highlights_raw)
        ]

        return {
            "id": tm.id,
            "team_a_id": req.team_a_id,
            "team_b_id": req.team_b_id,
            "score_a": round(score_a, 1),
            "score_b": round(score_b, 1),
            "captain_a_id": captain_a,
            "captain_b_id": captain_b,
            "match_ids": match_ids,
            "highlights": highlights,
            "created_at": tm.created_at.isoformat(),
        }


@app.post("/simulate/match")
def simulate_match(req: SimulateMatchRequest) -> dict[str, Any]:
    """
    Simulate a single match between two teams (first player from each team), persist and return.
    Phase 2: supports manual trigger for Explain flow.
    """
    import random
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
        events = list(orch.run())
        if not events:
            raise HTTPException(status_code=500, detail="Simulation produced no events")
        sets_needed = sets_to_win_match(req.best_of)
        last = events[-1]
        sets_a, sets_b = last.set_scores_after[0], last.set_scores_after[1]
        winner_id = player_a_id if sets_a >= sets_needed else player_b_id
        events_json = json.dumps([event_to_dict(e) for e in events])

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
    """Get a match by ID (with events and player names when available)."""
    with db_conn() as conn:
        match_repo = MatchRepository()
        match = match_repo.get(conn, match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="Match not found")
        p_a = get_player(conn, match.player_a_id)
        p_b = get_player(conn, match.player_b_id)
        out: dict[str, Any] = {
            "id": match.id,
            "team_a_id": match.team_a_id,
            "team_b_id": match.team_b_id,
            "player_a_id": match.player_a_id,
            "player_b_id": match.player_b_id,
            "player_a_name": p_a.name if p_a else match.player_a_id,
            "player_b_name": p_b.name if p_b else match.player_b_id,
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


@app.get("/analysis/match/{match_id}")
def get_analysis_match(match_id: str) -> dict[str, Any]:
    """
    Return deterministic, structured analytics for a match.
    No language generation — stats and outcome only. Includes rally/serve stats and player names.
    """
    with db_conn() as conn:
        match_repo = MatchRepository()
        match = match_repo.get(conn, match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="Match not found")
        events = []
        if match.events_json:
            events = json.loads(match.events_json)
        out = compute_match_analytics_fn(match, events)
        p_a = get_player(conn, match.player_a_id)
        p_b = get_player(conn, match.player_b_id)
        out["player_a_name"] = p_a.name if p_a else match.player_a_id
        out["player_b_name"] = p_b.name if p_b else match.player_b_id
        return out


@app.post("/explain/match", response_model=ExplainResponse)
def explain_match_endpoint(req: ExplainMatchRequest) -> ExplainResponse:
    """
    Generate a read-only LLM explanation of why a match turned out the way it did.
    Uses RAG pipeline: analytics + match summary + player context + rules → prompt → LLM.
    If OPENAI_API_KEY is not set, returns a stub response (no 503). Never influences simulation or persistence.
    """
    with db_conn() as conn:
        match_repo = MatchRepository()
        if match_repo.get(conn, req.match_id) is None:
            raise HTTPException(status_code=404, detail="Match not found")
        try:
            return explain_match(conn, req.match_id, req.user_query)
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Explanation failed: {e!s}. Use GET /analysis/match/{req.match_id} for analytics.",
            ) from e


# ---------- Run with: uvicorn backend.api:app --reload ----------
