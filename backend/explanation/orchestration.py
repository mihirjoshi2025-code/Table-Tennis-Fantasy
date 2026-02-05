"""
Agentic RAG orchestration for match explanations.

Pipeline (read-only, no simulation or persistence writes):
  1. Interpret user_query (optional) → decide which context sources to retrieve.
  2. Retrieve: match_summary, match_analytics, player_context, rules_context (from backend/analytics and DB reads only).
  3. Assemble context into a prompt; call LLM (or stub if no API key).
  4. Return explanation_text + supporting_facts; all claims traceable to retrieved data.

AI boundaries: This layer never calls simulation or scoring. It only reads match/analytics
and passes them to the LLM. Output is advisory; no fantasy team selection or autonomous agents.
"""
from __future__ import annotations

from typing import Any

from backend.explanation.llm import call_llm
from backend.explanation.prompt import build_prompt
from backend.explanation.retrieval import (
    get_match_analytics,
    get_match_summary,
    get_player_context,
    get_rules_context,
)
from backend.explanation.schemas import ContextBundle, ExplainResponse
from backend.persistence.repositories import MatchRepository


def decide_retrievals(user_query: str | None) -> list[str]:
    """
    Decide which context sources to retrieve based on the user query.
    Returns a list of source names; used for traceability and assembly.
    """
    q = (user_query or "").strip().lower()
    # Always include match outcome and analytics for "why" explanations
    sources = ["match_summary", "match_analytics"]
    # Player context helps for "why did X lose" or "who is"
    if any(kw in q for kw in ("why", "who", "player", "team", "lose", "win", "beat")):
        sources.append("player_context")
    else:
        sources.append("player_context")  # include by default for grounding
    sources.append("rules_context")
    return sources


def gather_context(conn: Any, match_id: str, user_query: str | None) -> ContextBundle:
    """
    Load match, decide retrievals, call retrieval functions, and assemble a context bundle.
    Sources used are recorded in bundle.sources_used.
    """
    sources = decide_retrievals(user_query)
    bundle = ContextBundle(sources_used=list(sources))

    match_repo = MatchRepository()
    match = match_repo.get(conn, match_id)
    if match is None:
        return bundle

    if "match_summary" in sources:
        bundle.match_summary = get_match_summary(conn, match_id)
    if "match_analytics" in sources:
        bundle.match_analytics = get_match_analytics(conn, match_id)
    if "player_context" in sources:
        bundle.player_context = get_player_context(
            conn, [match.player_a_id, match.player_b_id]
        )
    if "rules_context" in sources:
        bundle.rules_context = get_rules_context()

    return bundle


def explain_match(conn: Any, match_id: str, user_query: str | None = None) -> ExplainResponse:
    """
    Full explanation flow: gather context, build prompt, call LLM (or stub), return response.
    If OPENAI_API_KEY is not set, call_llm returns a stub so the endpoint still returns 200.
    """
    bundle = gather_context(conn, match_id, user_query)
    # If no match or no useful context, return a grounded fallback without calling LLM
    if bundle.match_summary is None:
        return ExplainResponse(
            explanation_text="No match data is available for this match ID.",
            supporting_facts=[],
        )
    if not bundle.match_analytics and not bundle.player_context:
        return ExplainResponse(
            explanation_text="Match was found but no analytics or player context could be loaded. Cannot generate a grounded explanation.",
            supporting_facts=["match_summary only"],
        )
    messages = build_prompt(bundle, user_query)
    explanation_text, supporting_facts = call_llm(messages)
    return ExplainResponse(
        explanation_text=explanation_text,
        supporting_facts=supporting_facts,
    )
