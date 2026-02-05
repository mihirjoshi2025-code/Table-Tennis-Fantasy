"""
Prompt template for the explanation feature.

Includes only retrieved facts (match summary, analytics, player context, rules).
Instructions to the LLM: stay grounded in the data; avoid speculation; explain why
the match turned out as it did; acknowledge uncertainty if data is missing. Output
is advisory; all claims must be traceable to structured analytics.
"""
from __future__ import annotations

import json
from typing import Any

from backend.explanation.schemas import ContextBundle


SYSTEM_INSTRUCTION = """You are a table tennis analyst. Your role is to explain match outcomes using only the data provided. You do not make decisions or influence any simulation or scoring.

Rules:
- Base every claim on the provided context. Do not invent stats or facts.
- Clearly separate facts (from the data) from interpretation (your reading of why they matter).
- If the data is insufficient to answer the question, say so explicitly.
- Acknowledge uncertainty when the data does not support a strong conclusion.
- Do not speculate about simulation internals, seeds, or randomness.
- Output must be advisory and explanatory, not authoritative."""


def _format_context(bundle: ContextBundle) -> str:
    """Format the context bundle as a single string for the prompt."""
    parts: list[str] = []

    if bundle.match_summary:
        parts.append("## Match summary (metadata)\n" + json.dumps(bundle.match_summary, indent=2))

    if bundle.match_analytics:
        parts.append("## Match analytics (deterministic stats)\n" + json.dumps(bundle.match_analytics, indent=2))

    if bundle.player_context:
        parts.append("## Player context (rankings)\n" + json.dumps(bundle.player_context, indent=2))

    if bundle.rules_context:
        parts.append("## Domain rules (table tennis)\n" + bundle.rules_context)

    if not parts:
        return "(No context available for this match.)"
    return "\n\n".join(parts)


def build_prompt(bundle: ContextBundle, user_query: str | None) -> list[dict[str, str]]:
    """
    Build the message list for the LLM: system + user with context and query.
    Returns a list of message dicts with "role" and "content".
    """
    context_block = _format_context(bundle)
    query = (user_query or "Explain why this match turned out the way it did.").strip()
    user_content = f"""Use only the following data. Do not add facts from outside this context.

{context_block}

---

User question: {query}

Respond with a short, grounded explanation. At the end, list the specific facts or stats you cited (supporting_facts) as a bullet list."""
    return [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": user_content},
    ]
