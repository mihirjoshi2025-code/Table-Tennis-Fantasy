"""
LLM invocation for the role advisory agent.

Uses the same OpenAI client as the explanation feature. If no API key, returns stub.
Advisory only: no tool calls, no state mutation.
"""
from __future__ import annotations

import json
import os
from typing import Any

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


STUB_EXPLANATION = (
    "Role advisor is disabled. Set OPENAI_API_KEY in the environment to get AI recommendations. "
    "Until then, use the role descriptions on the Create Team page to choose roles manually."
)


def _get_client() -> Any | None:
    if not HAS_OPENAI:
        return None
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def call_llm_advisor(messages: list[dict[str, str]]) -> tuple[list[dict[str, Any]], str, str | None]:
    """
    Call the LLM with advisor messages. Returns (recommendations, explanation, tradeoffs).
    recommendations: list of { player_id, player_name, suggested_role, why_fit, risk }.
    """
    client = _get_client()
    if client is None:
        return ([], STUB_EXPLANATION, None)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "role_advisor_response",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "recommendations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "player_id": {"type": "string"},
                                        "player_name": {"type": "string"},
                                        "suggested_role": {"type": "string"},
                                        "why_fit": {"type": "string"},
                                        "risk": {"type": "string"},
                                    },
                                    "required": ["player_id", "player_name", "suggested_role", "why_fit", "risk"],
                                    "additionalProperties": False,
                                },
                            },
                            "explanation": {"type": "string"},
                            "tradeoffs": {"type": "string"},
                        },
                        "required": ["recommendations", "explanation", "tradeoffs"],
                        "additionalProperties": False,
                    },
                },
            },
            max_tokens=1024,
        )
    except Exception as e:
        return (
            [],
            f"The role advisor encountered an error: {e!s}. Choose roles manually using the role descriptions.",
            None,
        )

    choice = response.choices[0]
    if not choice.message.content:
        return ([], "No response generated.", None)
    try:
        data = json.loads(choice.message.content)
        recs = data.get("recommendations", [])
        if not isinstance(recs, list):
            recs = []
        explanation = (data.get("explanation") or "").strip() or "No explanation."
        tradeoffs = data.get("tradeoffs")
        if tradeoffs is not None:
            tradeoffs = str(tradeoffs).strip() or None
        return (recs, explanation, tradeoffs)
    except (json.JSONDecodeError, TypeError):
        return ([], "The advisor response could not be parsed.", None)
