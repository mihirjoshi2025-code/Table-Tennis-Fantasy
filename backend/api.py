"""
REST API for the table tennis fantasy backend.
Thin wrappers around domain logic and persistence.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Generator

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
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
    LeagueRepository,
    LeagueMemberRepository,
    SeasonRepository,
    WeekRepository,
    LeagueMatchRepository,
)
from backend.persistence.repositories import _has_col
from backend.services.league_service import LeagueService, LeagueTransitionError
from backend.analytics import (
    compute_match_analytics as compute_match_analytics_fn,
    compute_league_match_slot_data,
    compute_total_match_momentum,
)
from backend.explanation import ExplainResponse, explain_match
from backend.role_advisor import RoleAdvisorResponse, advise_roles
from backend.persistence.db import get_db_path
from backend.scoring import aggregate_stats_from_events, compute_fantasy_score
from backend.roles import Role, parse_role, list_all_roles
from backend.services.simulation_service import run_team_match_simulation
from backend.simulation.persistence import event_to_dict
from backend.simulation.schemas import MatchConfig
from backend.simulation.orchestrator import MatchOrchestrator, sets_to_win_match
from backend.rankings_db import build_profile_store_for_match
from backend.live_match_engine import run_live_league_match_with_delays


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
    role: str | None = Field(None, description="One of: anchor, aggressor, closer, wildcard, stabilizer. Only for slots 1-7; at most one per role per team.")


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


class CreateLeagueRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    max_teams: int = Field(..., ge=2, le=20, description="Max teams (players) in league")


class JoinLeagueRequest(BaseModel):
    team_id: str = Field(..., description="User's team to use in this league")
    user_id: str | None = Field(None, description="Override; default from JWT")


class FastForwardWeekRequest(BaseModel):
    seed: int | None = Field(None, description="RNG seed for deterministic demo")


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


@app.get("/roles")
def list_roles() -> dict[str, Any]:
    """List all player roles with definitions (for team create/edit UI)."""
    roles = [
        {"id": r.value, "name": d.name, "description": d.description, "modifier_summary": d.modifier_summary}
        for r, d in list_all_roles()
    ]
    return {"roles": roles}


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
            # Role validation: only slots 1-7; at most one per role per team; valid role names
            roles_used: list[str] = []
            for r in req.roster:
                if r.role:
                    if r.slot > TEAM_ACTIVE:
                        raise HTTPException(
                            status_code=400,
                            detail="Role can only be assigned to active slots (1-7), not bench",
                        )
                    parsed = parse_role(r.role)
                    if parsed is None:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid role '{r.role}'. Must be one of: anchor, aggressor, closer, wildcard, stabilizer",
                        )
                    if parsed.value in roles_used:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Each role can appear at most once per team (duplicate: {parsed.value})",
                        )
                    roles_used.append(parsed.value)
            def _role_value(slot_role: str | None) -> str | None:
                p = parse_role(slot_role) if slot_role else None
                return p.value if p else None
            roster_tuples = [(r.player_id, r.slot, r.is_captain, _role_value(r.role)) for r in req.roster]
            team = team_repo.create_phase2(conn, uid, req.name, req.gender, req.budget, roster_tuples)
            with_slots = team_repo.get_players_with_slots(conn, team.id)
            return {
                "id": team.id,
                "user_id": team.user_id,
                "name": team.name,
                "gender": team.gender,
                "budget": team.budget,
                "roster": [{"player_id": p, "slot": s, "is_captain": c, "role": role} for p, s, c, role in (tuple(r) for r in with_slots)],
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
                    "player_id": r[0],
                    "slot": r[1],
                    "is_captain": r[2],
                    "role": r[3] if len(r) > 3 else None,
                    "last_match_points": _last_match_points_for_player(conn, match_repo, r[0]),
                }
                for r in with_slots
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
                "role_log": h.get("role_log", []),
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


# ---------- Leagues (Step 3) ----------


def _compute_league_standings(conn, league_id: str) -> list[dict[str, Any]]:
    """Compute standings from completed league_matches. Returns list of {team_id, wins, losses, draws, points_for, points_against, differential}."""
    season_repo = SeasonRepository()
    week_repo = WeekRepository()
    league_match_repo = LeagueMatchRepository()
    season = season_repo.get_current_for_league(conn, league_id)
    if season is None:
        return []
    weeks = week_repo.list_by_season(conn, season.id)
    by_team: dict[str, dict[str, Any]] = {}
    for w in weeks:
        for m in league_match_repo.list_by_week(conn, w.id):
            if m.status != "completed":
                continue
            home_id = m.home_team_id
            away_id = m.away_team_id
            pairs = [(home_id, m.home_score, m.away_score)]
            if away_id:
                pairs.append((away_id, m.away_score, m.home_score))
            for tid, pts_for, pts_against in pairs:
                if tid not in by_team:
                    by_team[tid] = {"team_id": tid, "wins": 0, "losses": 0, "draws": 0, "points_for": 0.0, "points_against": 0.0}
                by_team[tid]["points_for"] += pts_for
                by_team[tid]["points_against"] += pts_against
                if away_id is None:
                    continue  # bye: no W/L/D
                if pts_for > pts_against:
                    by_team[tid]["wins"] += 1
                elif pts_for < pts_against:
                    by_team[tid]["losses"] += 1
                else:
                    by_team[tid]["draws"] += 1
    for t in by_team.values():
        t["differential"] = round(t["points_for"] - t["points_against"], 1)
    return sorted(by_team.values(), key=lambda x: (-x["wins"], -x["differential"], -x["points_for"]))


@app.post("/leagues")
def create_league(
    req: CreateLeagueRequest,
    user_id_from_token: str | None = Depends(_get_current_user_id),
) -> dict[str, Any]:
    """Create a league. Creator is owner; league starts in 'open' status."""
    if not user_id_from_token:
        raise HTTPException(status_code=401, detail="Login required to create league")
    with db_conn() as conn:
        league_repo = LeagueRepository()
        league = league_repo.create(conn, req.name, user_id_from_token, req.max_teams)
        return {
            "id": league.id,
            "name": league.name,
            "creator_user_id": league.owner_id,
            "owner_id": league.owner_id,
            "status": league.status,
            "max_teams": league.max_teams,
            "created_at": league.created_at.isoformat(),
        }


@app.get("/leagues")
def list_leagues(
    mine: bool = Query(False, description="If true and user is logged in, return only leagues the user owns or is a member of"),
    user_id_from_token: str | None = Depends(_get_current_user_id),
) -> dict[str, Any]:
    """List leagues. With mine=true and auth, returns only leagues the user owns or has joined."""
    with db_conn() as conn:
        league_repo = LeagueRepository()
        member_repo = LeagueMemberRepository()
        leagues = league_repo.list_all(conn)
        if mine and user_id_from_token:
            member_league_ids = set(member_repo.list_league_ids_by_user(conn, user_id_from_token))
            leagues = [l for l in leagues if l.owner_id == user_id_from_token or l.id in member_league_ids]
        return {
            "leagues": [
                {
                    "id": l.id,
                    "name": l.name,
                    "creator_user_id": l.owner_id,
                    "owner_id": l.owner_id,
                    "status": l.status,
                    "max_teams": l.max_teams,
                    "created_at": l.created_at.isoformat(),
                }
                for l in leagues
            ],
        }


@app.get("/leagues/{league_id}")
def get_league(league_id: str) -> dict[str, Any]:
    """Get league by ID with members and current week/schedule summary."""
    with db_conn() as conn:
        league_repo = LeagueRepository()
        member_repo = LeagueMemberRepository()
        season_repo = SeasonRepository()
        week_repo = WeekRepository()
        league_match_repo = LeagueMatchRepository()
        league = league_repo.get(conn, league_id)
        if league is None:
            raise HTTPException(status_code=404, detail="League not found")
        members = member_repo.list_by_league(conn, league_id)
        team_repo = TeamRepository()
        members_with_teams: list[dict[str, Any]] = []
        for m in members:
            team = team_repo.get(conn, m.team_id)
            members_with_teams.append({
                "user_id": m.user_id,
                "team_id": m.team_id,
                "team_name": team.name if team else None,
                "joined_at": m.joined_at.isoformat(),
            })
        out: dict[str, Any] = {
            "id": league.id,
            "name": league.name,
            "creator_user_id": league.owner_id,
            "owner_id": league.owner_id,
            "status": league.status,
            "max_teams": league.max_teams,
            "created_at": league.created_at.isoformat(),
            "members": members_with_teams,
        }
        if league.started_at is not None:
            out["started_at"] = league.started_at.isoformat()
        season = season_repo.get_current_for_league(conn, league_id)
        if season:
            out["current_week"] = season.current_week
            out["total_weeks"] = season.total_weeks
            week = week_repo.get_by_season_and_number(conn, season.id, season.current_week)
            if week:
                matches = league_match_repo.list_by_week(conn, week.id)
                out["current_week_matches"] = [
                    {"id": m.id, "home_team_id": m.home_team_id, "away_team_id": m.away_team_id, "status": m.status, "home_score": m.home_score, "away_score": m.away_score}
                    for m in matches
                ]
            # Full schedule: all weeks and matches (deterministic, persisted)
            weeks = week_repo.list_by_season(conn, season.id)
            out["schedule"] = [
                {
                    "week_number": w.week_number,
                    "week_id": w.id,
                    "matches": [
                        {"id": m.id, "home_team_id": m.home_team_id, "away_team_id": m.away_team_id, "status": m.status, "home_score": m.home_score, "away_score": m.away_score}
                        for m in league_match_repo.list_by_week(conn, w.id)
                    ],
                }
                for w in weeks
            ]
        return out


@app.post("/leagues/{league_id}/join")
def join_league(
    league_id: str,
    req: JoinLeagueRequest,
    user_id_from_token: str | None = Depends(_get_current_user_id),
) -> dict[str, Any]:
    """Join a league with a team. One team per user per league. League must be open."""
    uid = user_id_from_token or req.user_id
    if not uid:
        raise HTTPException(status_code=401, detail="Login or user_id required to join league")
    with db_conn() as conn:
        league_repo = LeagueRepository()
        member_repo = LeagueMemberRepository()
        team_repo = TeamRepository()
        league = league_repo.get(conn, league_id)
        if league is None:
            raise HTTPException(status_code=404, detail="League not found")
        if league.status != "open":
            raise HTTPException(status_code=400, detail="League is not open for new members")
        existing = member_repo.get(conn, league_id, uid)
        if existing:
            raise HTTPException(status_code=400, detail="Already in this league")
        members = member_repo.list_by_league(conn, league_id)
        if len(members) >= league.max_teams:
            raise HTTPException(status_code=400, detail="League is full")
        team = team_repo.get(conn, req.team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")
        if team.user_id != uid:
            raise HTTPException(status_code=403, detail="Team must belong to you")
        active = team_repo.get_active_player_ids(conn, req.team_id)
        if len(active) != TEAM_ACTIVE:
            raise HTTPException(status_code=400, detail="Team must have exactly 7 active players (slots 1-7)")
        member_repo.create(conn, league_id, uid, req.team_id)
        # Optionally set team.league_id for consistency
        conn.execute("UPDATE teams SET league_id = ? WHERE id = ?", (league_id, req.team_id))
        conn.commit()
        return {"league_id": league_id, "user_id": uid, "team_id": req.team_id, "joined": True}


@app.post("/leagues/{league_id}/start")
def start_league(
    league_id: str,
    user_id_from_token: str | None = Depends(_get_current_user_id),
) -> dict[str, Any]:
    """Start league: freeze membership, generate round-robin schedule. Only league owner; league must be open; at least 2 teams."""
    if not user_id_from_token:
        raise HTTPException(status_code=401, detail="Login required to start league")
    with db_conn() as conn:
        league_repo = LeagueRepository()
        league = league_repo.get(conn, league_id)
        if league is None:
            raise HTTPException(status_code=404, detail="League not found")
        if league.owner_id != user_id_from_token:
            raise HTTPException(status_code=403, detail="Only the league owner can start the league")
        svc = LeagueService()
        try:
            svc.start_league(conn, league_id)
        except LeagueTransitionError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            if "transition" in str(e).lower() or "open" in str(e).lower():
                raise HTTPException(status_code=400, detail=str(e))
            raise HTTPException(status_code=500, detail=str(e))
        league = league_repo.get(conn, league_id)
        started_at = league.started_at.isoformat() if league and league.started_at else None
        return {"league_id": league_id, "status": "active", "started": True, "started_at": started_at}


@app.post("/leagues/{league_id}/fast-forward-week")
def fast_forward_week(
    league_id: str,
  req: FastForwardWeekRequest | None = None,
) -> dict[str, Any]:
    """Run all matches for the current week, persist results, advance week. Demo mode."""
    with db_conn() as conn:
        svc = LeagueService()
        try:
            svc.fast_forward_week(conn, league_id, seed=req.seed if req else None)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            if "transition" in str(e).lower() or "active" in str(e).lower():
                raise HTTPException(status_code=400, detail=str(e))
            raise HTTPException(status_code=500, detail=str(e))
        league_repo = LeagueRepository()
        season_repo = SeasonRepository()
        league = league_repo.get(conn, league_id)
        season = season_repo.get_current_for_league(conn, league_id)
        return {
            "league_id": league_id,
            "advanced": True,
            "current_week": season.current_week if season else None,
            "total_weeks": season.total_weeks if season else None,
            "league_completed": league.status == "completed" if league else False,
        }


@app.get("/leagues/{league_id}/standings")
def get_league_standings(league_id: str) -> dict[str, Any]:
    """Get league standings: wins, losses, draws, points_for, points_against, differential."""
    with db_conn() as conn:
        league_repo = LeagueRepository()
        league = league_repo.get(conn, league_id)
        if league is None:
            raise HTTPException(status_code=404, detail="League not found")
        rows = _compute_league_standings(conn, league_id)
        return {"league_id": league_id, "standings": rows}


# ---------- Live league match (Step 4): in-memory state + WebSocket ----------
# Concurrency: live state and connections are process-local; background task runs simulation and pushes to WebSocket.
# Late join: when status is live, GET and WebSocket always return current state (bootstrap if not in memory).

_live_match_state: dict[str, dict[str, Any]] = {}  # match_id -> {elapsed_seconds, home_score, away_score, highlights, done, games}
_live_connections: dict[str, list[WebSocket]] = {}  # match_id -> list of WebSocket


def _build_live_bootstrap(conn, match_id: str) -> dict[str, Any]:
    """Build initial live state for late join: 0-0, 7 games with player names, all pending. Source of truth for 'match is live'."""
    league_match_repo = LeagueMatchRepository()
    team_repo = TeamRepository()
    m = league_match_repo.get(conn, match_id)
    if m is None or m.away_team_id is None:
        return {
            "elapsed_seconds": 0,
            "home_score": 0.0,
            "away_score": 0.0,
            "highlights": [],
            "done": False,
            "games": [],
        }
    active_home = team_repo.get_active_player_ids(conn, m.home_team_id)
    active_away = team_repo.get_active_player_ids(conn, m.away_team_id)
    games: list[dict[str, Any]] = []
    for i in range(7):
        pid_h = active_home[i] if i < len(active_home) else ""
        pid_a = active_away[i] if i < len(active_away) else ""
        p_h = get_player(conn, pid_h) if pid_h else None
        p_a = get_player(conn, pid_a) if pid_a else None
        games.append({
            "slot": i + 1,
            "home_player_id": pid_h,
            "away_player_id": pid_a,
            "home_player_name": p_h.name if p_h else pid_h or "—",
            "away_player_name": p_a.name if p_a else pid_a or "—",
            "score_home": 0.0,
            "score_away": 0.0,
            "status": "pending",
        })
    return {
        "elapsed_seconds": 0,
        "home_score": 0.0,
        "away_score": 0.0,
        "highlights": [],
        "done": False,
        "games": games,
    }


@app.get("/league-matches/{match_id}")
def get_league_match(match_id: str) -> dict[str, Any]:
    """Get league match by ID. Includes team names and current live state if match is live. Late join: when status=live, always return live state (bootstrap from DB if not in memory)."""
    with db_conn() as conn:
        league_match_repo = LeagueMatchRepository()
        team_repo = TeamRepository()
        m = league_match_repo.get(conn, match_id)
        if m is None:
            raise HTTPException(status_code=404, detail="League match not found")
        home_team = team_repo.get(conn, m.home_team_id)
        away_team = team_repo.get(conn, m.away_team_id) if m.away_team_id else None
        out: dict[str, Any] = {
            "id": m.id,
            "week_id": m.week_id,
            "home_team_id": m.home_team_id,
            "away_team_id": m.away_team_id,
            "home_team_name": home_team.name if home_team else m.home_team_id,
            "away_team_name": away_team.name if away_team else (m.away_team_id or "Bye"),
            "home_score": m.home_score,
            "away_score": m.away_score,
            "status": m.status,
            "simulation_log": m.simulation_log,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        if m.status == "live":
            live = _live_match_state.get(match_id)
            if not live:
                live = _build_live_bootstrap(conn, match_id)
            out["live"] = {
                "elapsed_seconds": live.get("elapsed_seconds", 0),
                "home_score": live.get("home_score", 0),
                "away_score": live.get("away_score", 0),
                "highlights": live.get("highlights", []),
                "done": live.get("done", False),
                "games": live.get("games", []),
            }
        else:
            live = _live_match_state.get(match_id)
            if live:
                out["live"] = {
                    "elapsed_seconds": live.get("elapsed_seconds"),
                    "home_score": live.get("home_score"),
                    "away_score": live.get("away_score"),
                    "highlights": live.get("highlights", []),
                    "done": live.get("done", False),
                    "games": live.get("games", []),
                }
        if m.status == "completed" and _has_col(conn, "league_matches", "slot_data"):
            row = conn.execute("SELECT slot_data FROM league_matches WHERE id = ?", (match_id,)).fetchone()
            if row and row[0]:
                slot_data = json.loads(row[0])
                out["slot_data"] = slot_data
                out["total_momentum"] = compute_total_match_momentum(slot_data)
        return out


class StartLiveRequest(BaseModel):
    seed: int | None = Field(None, description="RNG seed for deterministic demo")


class FastForwardMatchRequest(BaseModel):
    seed: int | None = None


@app.post("/league-matches/{match_id}/start-live")
async def start_live_league_match(
    match_id: str,
    req: StartLiveRequest | None = None,
) -> dict[str, Any]:
    """
    Start live simulation: match status -> live, run simulation over ~4–5 min in background
    (35s per game × 7 games), push updates to WebSocket. Persist result and set status=completed when done.
    Returns immediately; clients subscribe via WebSocket for updates.
    """
    with db_conn() as conn:
        league_match_repo = LeagueMatchRepository()
        m = league_match_repo.get(conn, match_id)
        if m is None:
            raise HTTPException(status_code=404, detail="League match not found")
        if m.status == "live":
            return {"match_id": match_id, "status": "live", "message": "Already live"}
        if m.status == "completed":
            return {"match_id": match_id, "status": "completed", "message": "Already completed"}
        if m.away_team_id is None:
            league_match_repo.update_result(conn, match_id, 0.0, 0.0, simulation_log="Bye")
            return {"match_id": match_id, "status": "completed", "message": "Bye"}
        league_match_repo.update_status(conn, match_id, "live")
        bootstrap = _build_live_bootstrap(conn, match_id)
        _live_match_state[match_id] = bootstrap
    seed = (req.seed if req else None)
    asyncio.create_task(_run_live_task(match_id, seed))
    return {"match_id": match_id, "status": "live", "started": True}


async def _run_live_task(match_id: str, seed: int | None) -> None:
    """Background task: run live simulation, push to WebSocket, persist when done. Bootstrap already set by start_live; initial tick sent immediately so late join gets state."""
    def get_conn():
        return get_connection()

    async def on_tick(elapsed: float, home: float, away: float, hl: list, done: bool):
        current = _live_match_state.get(match_id, {})
        games = list(current.get("games", []))
        for i, h in enumerate(hl):
            if i < len(games):
                g = dict(games[i])
                g["score_home"] = float(h.get("points_home", 0))
                g["score_away"] = float(h.get("points_away", 0))
                g["status"] = "completed"
                games[i] = g
        state = {
            **current,
            "elapsed_seconds": round(elapsed, 1),
            "home_score": home,
            "away_score": away,
            "highlights": hl,
            "done": done,
            "games": games,
        }
        _live_match_state[match_id] = state
        payload = {"type": "live_update", "elapsed_seconds": state["elapsed_seconds"], "home_score": home, "away_score": away, "highlights": hl, "done": done, "games": games}
        for ws in _live_connections.get(match_id, [])[:]:
            try:
                await ws.send_json(payload)
            except Exception:
                pass
        if done:
            _live_match_state.pop(match_id, None)

    # Send initial tick immediately so late subscribers and GET see 0-0 and games list without waiting for simulation.
    await on_tick(0.0, 0.0, 0.0, [], False)
    result = await run_live_league_match_with_delays(get_conn, match_id, seed=seed, on_tick_async=on_tick)
    # Persist with slot_data after simulation returns (on_tick(done) only clears in-memory state).
    if result and result.get("slot_details"):
        slot_data = compute_league_match_slot_data(result["slot_details"])
        home = result["home_score"]
        away = result["away_score"]
        import concurrent.futures
        loop = asyncio.get_event_loop()
        def persist():
            c = get_connection()
            try:
                LeagueMatchRepository().update_result(
                    c, match_id, home, away,
                    simulation_log="Live completed",
                    slot_data_json=json.dumps(slot_data),
                )
            finally:
                c.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            await loop.run_in_executor(ex, persist)


@app.post("/league-matches/{match_id}/fast-forward")
def fast_forward_league_match(
    match_id: str,
    req: FastForwardMatchRequest | None = None,
) -> dict[str, Any]:
    """
    Resolve match immediately: run simulation, persist result, set status=completed.
    Same final result as live; no real-time stream.
    """
    with db_conn() as conn:
        league_match_repo = LeagueMatchRepository()
        m = league_match_repo.get(conn, match_id)
        if m is None:
            raise HTTPException(status_code=404, detail="League match not found")
        if m.status == "completed":
            return {"match_id": match_id, "status": "completed", "home_score": m.home_score, "away_score": m.away_score}
        if m.away_team_id is None:
            league_match_repo.update_result(conn, match_id, 0.0, 0.0, simulation_log="Bye")
            return {"match_id": match_id, "status": "completed", "home_score": 0.0, "away_score": 0.0}
        result = run_team_match_simulation(
            conn, m.home_team_id, m.away_team_id, seed=req.seed if req else None, best_of=5
        )
        slot_data = compute_league_match_slot_data(result.get("slot_details", []))
        league_match_repo.update_result(
            conn, match_id,
            result["home_score"], result["away_score"],
            simulation_log=result.get("explanation"),
            slot_data_json=json.dumps(slot_data),
        )
        return {
            "match_id": match_id,
            "status": "completed",
            "home_score": result["home_score"],
            "away_score": result["away_score"],
            "highlights": result.get("highlights", []),
        }


@app.get("/league-matches/{match_id}/games/{slot}")
def get_league_match_game(match_id: str, slot: int) -> dict[str, Any]:
    """
    Get one game (slot 1–7) data for a completed league match: TT momentum series, analytics, player names.
    Used for per-game visualization and AI summary.
    """
    if slot < 1 or slot > 7:
        raise HTTPException(status_code=400, detail="Slot must be 1–7")
    with db_conn() as conn:
        league_match_repo = LeagueMatchRepository()
        m = league_match_repo.get(conn, match_id)
        if m is None:
            raise HTTPException(status_code=404, detail="League match not found")
        if m.status != "completed":
            raise HTTPException(status_code=400, detail="Match not completed; slot data available after completion")
        if not _has_col(conn, "league_matches", "slot_data"):
            raise HTTPException(status_code=404, detail="Slot data not available for this match")
        row = conn.execute("SELECT slot_data FROM league_matches WHERE id = ?", (match_id,)).fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=404, detail="Slot data not available for this match")
        slot_data = json.loads(row[0])
        if slot > len(slot_data):
            raise HTTPException(status_code=404, detail="Game not found")
        s = slot_data[slot - 1]
        home_id = s.get("home_player_id", "")
        away_id = s.get("away_player_id", "")
        home_team = TeamRepository().get(conn, m.home_team_id)
        away_team = TeamRepository().get(conn, m.away_team_id) if m.away_team_id else None
        p_h = get_player(conn, home_id)
        p_a = get_player(conn, away_id)
        return {
            "match_id": match_id,
            "slot": slot,
            "home_team_name": home_team.name if home_team else m.home_team_id,
            "away_team_name": away_team.name if away_team else (m.away_team_id or "Bye"),
            "home_player_id": home_id,
            "away_player_id": away_id,
            "home_player_name": p_h.name if p_h else home_id,
            "away_player_name": p_a.name if p_a else away_id,
            "momentum_series": s.get("momentum_series", []),
            "total_points": s.get("total_points", 0),
            "longest_rally": s.get("longest_rally"),
            "avg_rally_length": s.get("avg_rally_length"),
            "serve_win_pct_a": s.get("serve_win_pct_a"),
            "serve_win_pct_b": s.get("serve_win_pct_b"),
            "player_a_stats": s.get("player_a_stats"),
            "player_b_stats": s.get("player_b_stats"),
            "winner_id": s.get("winner_id"),
        }


class ExplainLeagueMatchGameRequest(BaseModel):
    league_match_id: str
    slot: int


@app.post("/explain/league-match-game", response_model=ExplainResponse)
def explain_league_match_game_endpoint(req: ExplainLeagueMatchGameRequest) -> ExplainResponse:
    """
    Generate an AI summary of one game (slot 1–7) of a completed league match.
    Uses stats: forehand/backhand/service winners, serve %, unforced errors, rally length.
    If OPENAI_API_KEY is not set, returns a stub.
    """
    if req.slot < 1 or req.slot > 7:
        raise HTTPException(status_code=400, detail="Slot must be 1–7")
    with db_conn() as conn:
        league_match_repo = LeagueMatchRepository()
        m = league_match_repo.get(conn, req.league_match_id)
        if m is None:
            raise HTTPException(status_code=404, detail="League match not found")
        if not _has_col(conn, "league_matches", "slot_data"):
            raise HTTPException(status_code=404, detail="Slot data not available")
        row = conn.execute("SELECT slot_data FROM league_matches WHERE id = ?", (req.league_match_id,)).fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=404, detail="Slot data not available")
        slot_data = json.loads(row[0])
        if req.slot > len(slot_data):
            raise HTTPException(status_code=404, detail="Game not found")
        s = slot_data[req.slot - 1]
        home_id = s.get("home_player_id", "")
        away_id = s.get("away_player_id", "")
        p_h = get_player(conn, home_id)
        p_a = get_player(conn, away_id)
        home_name = p_h.name if p_h else home_id
        away_name = p_a.name if p_a else away_id
        stats_a = s.get("player_a_stats") or {}
        stats_b = s.get("player_b_stats") or {}
        serve_a = s.get("serve_win_pct_a")
        serve_b = s.get("serve_win_pct_b")
        total_pts = s.get("total_points", 0)
        longest_rally = s.get("longest_rally")
        avg_rally = s.get("avg_rally_length")
        context = (
            f"Game {req.slot}: {home_name} (home) vs {away_name} (away). "
            f"Total table tennis points played: {total_pts}. "
            f"Longest rally: {longest_rally} shots. Average rally length: {avg_rally}. "
            f"Home serve win %: {serve_a}%. Away serve win %: {serve_b}%. "
            f"Home stats: forehand winners {stats_a.get('forehand_winners', 0)}, backhand winners {stats_a.get('backhand_winners', 0)}, "
            f"service winners {stats_a.get('service_winners', 0)}, unforced errors {stats_a.get('unforced_errors', 0)}. "
            f"Away stats: forehand winners {stats_b.get('forehand_winners', 0)}, backhand winners {stats_b.get('backhand_winners', 0)}, "
            f"service winners {stats_b.get('service_winners', 0)}, unforced errors {stats_b.get('unforced_errors', 0)}."
        )
        from backend.explanation.llm import call_llm
        messages = [
            {"role": "system", "content": "You are a table tennis analyst. Summarize this game in 2–4 sentences. Mention specific stats: how many winners each player hit (forehand, backhand, service), serve performance, unforced errors, and any notable rallies or momentum shifts. Be factual and use only the provided statistics."},
            {"role": "user", "content": context},
        ]
        explanation_text, supporting_facts = call_llm(messages)
        return ExplainResponse(explanation_text=explanation_text, supporting_facts=supporting_facts)


@app.post("/league-matches/{match_id}/restart")
def restart_league_match(match_id: str) -> dict[str, Any]:
    """
    Reset a league match to scheduled (for testing). Clears scores and simulation_log
    so you can run live or fast-forward again.
    """
    with db_conn() as conn:
        league_match_repo = LeagueMatchRepository()
        m = league_match_repo.get(conn, match_id)
        if m is None:
            raise HTTPException(status_code=404, detail="League match not found")
        league_match_repo.reset_to_scheduled(conn, match_id)
    _live_match_state.pop(match_id, None)
    return {"match_id": match_id, "status": "scheduled", "restarted": True}


@app.websocket("/ws/league-match/{match_id}")
async def websocket_league_match(websocket: WebSocket, match_id: str):
    """
    Subscribe to live updates for a league match. Server pushes { type: "live_update", elapsed_seconds, home_score, away_score, highlights, done, games }.
    Late join: on connect, immediately send current state (bootstrap from DB if match is live but state not in memory).
    """
    await websocket.accept()
    if match_id not in _live_connections:
        _live_connections[match_id] = []
    _live_connections[match_id].append(websocket)
    try:
        state = _live_match_state.get(match_id)
        if not state:
            with db_conn() as conn:
                m = LeagueMatchRepository().get(conn, match_id)
                if m and m.status == "live":
                    state = _build_live_bootstrap(conn, match_id)
        if state:
            await websocket.send_json({"type": "live_update", **state})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if match_id in _live_connections:
            _live_connections[match_id] = [w for w in _live_connections[match_id] if w != websocket]
            if not _live_connections[match_id]:
                del _live_connections[match_id]


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


# ---------- Role advisor (advisory only; never modifies team or roles) ----------
class RoleAdvisorRequest(BaseModel):
    query: str = Field(..., min_length=1, description="e.g. 'Who should I assign as my Aggressor?'")
    team_id: str | None = Field(None, description="Optional: scope to this team's roster")
    gender: str | None = Field(None, description="Optional: scope to men or women if no team_id")


@app.post("/advise/roles")
def advise_roles_endpoint(req: RoleAdvisorRequest) -> dict[str, Any]:
    """
    AI role advisor: recommends which players suit which roles. Read-only; does not assign roles.
    Provide team_id (for roster) or gender (for pool). If OPENAI_API_KEY is not set, returns stub.
    """
    with db_conn() as conn:
        if req.team_id:
            team_repo = TeamRepository()
            if team_repo.get(conn, req.team_id) is None:
                raise HTTPException(status_code=404, detail="Team not found")
        try:
            response = advise_roles(conn, req.query, team_id=req.team_id, gender=req.gender)
            return response.to_dict()
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Role advisor failed: {e!s}. Choose roles manually using the role descriptions.",
            ) from e


# ---------- Run with: uvicorn backend.api:app --reload ----------
