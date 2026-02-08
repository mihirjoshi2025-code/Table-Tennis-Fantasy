"""
Orchestration for the role advisory agent. Read-only; no team or role mutation.

Pipeline:
  1. Resolve player list (from team_id or from query / gender).
  2. Data retrieval: player stats via data adapter.
  3. Build prompt with role profiles + player stats + query.
  4. Call LLM (or stub); parse into RoleAdvisorResponse.

Advice ≠ automation: the agent recommends; the user assigns. Role mechanics are validated
in backend/tests/test_role_scoring.py (role-specific scoring, regression, explainability).
"""
from __future__ import annotations

from typing import Any

from backend.persistence.repositories import TeamRepository
from backend.rankings_db import list_players_by_gender
from backend.role_advisor.data_adapter import get_player_stats_for_advisor
from backend.role_advisor.llm import call_llm_advisor
from backend.role_advisor.profiles import ROLE_PROFILES
from backend.role_advisor.prompt import build_advisor_prompt
from backend.role_advisor.schemas import RoleAdvisorResponse, RoleRecommendation


def _resolve_player_ids(conn: Any, team_id: str | None, gender: str | None, limit: int = 60) -> list[str]:
    """Resolve player list: from team roster, or from gender-filtered rankings. Use 60 when by gender so we have players in tiers 1-10, 11-20, 21+."""
    if team_id:
        team_repo = TeamRepository()
        ids = team_repo.get_players(conn, team_id)
        return ids[:limit] if ids else []
    if gender:
        rows = list_players_by_gender(conn, gender, limit=limit)
        return [r.id for r in rows]
    return []


def advise_roles(
    conn: Any,
    query: str,
    team_id: str | None = None,
    gender: str | None = None,
) -> RoleAdvisorResponse:
    """
    Run the role advisory flow: gather player stats, build prompt, call LLM, return recommendations.
    Does not modify team data or assign roles. Advisory only.
    """
    player_ids = _resolve_player_ids(conn, team_id, gender)
    if not player_ids:
        return RoleAdvisorResponse(
            recommendations=[],
            explanation="No players in context. Provide a team_id or gender to get role recommendations.",
            tradeoffs=None,
        )
    player_stats = get_player_stats_for_advisor(conn, player_ids)
    if not player_stats:
        return RoleAdvisorResponse(
            recommendations=[],
            explanation="Could not load player statistics. Check that the team or gender has valid players.",
            tradeoffs=None,
        )
    messages = build_advisor_prompt(player_stats, ROLE_PROFILES, query.strip())
    recs_raw, explanation, tradeoffs = call_llm_advisor(messages)
    recommendations: list[RoleRecommendation] = []
    for r in recs_raw:
        if isinstance(r, dict) and r.get("player_id") and r.get("suggested_role"):
            recommendations.append(RoleRecommendation(
                player_id=str(r["player_id"]),
                player_name=str(r.get("player_name", r["player_id"])),
                suggested_role=str(r["suggested_role"]),
                why_fit=str(r.get("why_fit", "")),
                risk=str(r.get("risk", "")),
            ))
    return RoleAdvisorResponse(
        recommendations=recommendations,
        explanation=explanation,
        tradeoffs=tradeoffs,
    )
