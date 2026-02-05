"""
LLM invocation for the explanation feature.

Configurable via OPENAI_API_KEY. If no key is set (or openai is not installed),
returns a stub response so the endpoint still works end-to-end. No tool calls,
no memory; deterministic temperature. All claims are traceable to retrieved context.

AI boundary: This module is the only place that calls an external LLM. Simulation
and scoring are never invoked here. Output is advisory and read-only.
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


class ExplanationUnavailableError(Exception):
    """Raised only when caller needs to distinguish hard failure (e.g. missing dependency)."""
    pass


# Stub response when LLM is not configured (no API key or no openai package).
STUB_EXPLANATION = (
    "LLM explanation is disabled. Set OPENAI_API_KEY in the environment where the API server runs to enable natural-language explanations. "
    "Until then, use GET /analysis/match/{id} for deterministic analytics."
)
STUB_FACTS = ["Stub: OPENAI_API_KEY not set or openai package not installed."]


def _get_client() -> Any | None:
    """
    Return OpenAI client if API key is set and openai is installed.
    Returns None if no key or missing package — caller should use stub response.
    """
    if not HAS_OPENAI:
        return None
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def call_llm(messages: list[dict[str, str]]) -> tuple[str, list[str]]:
    """
    Call the LLM with the given messages. Returns (explanation_text, supporting_facts).

    If OPENAI_API_KEY is not set or openai is not installed, returns a stub response
    so the endpoint remains usable and deterministic. Uses temperature=0 when the
    real client is used. All claims in real responses are grounded in the provided
    context; if data is insufficient, the model is instructed to say so.
    """
    client = _get_client()
    if client is None:
        return (STUB_EXPLANATION, STUB_FACTS)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "explanation_response",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "explanation_text": {
                            "type": "string",
                            "description": "Short, grounded explanation based only on the provided data.",
                        },
                        "supporting_facts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of specific facts or stats cited from the context.",
                        },
                    },
                    "required": ["explanation_text", "supporting_facts"],
                    "additionalProperties": False,
                },
            },
        },
        max_tokens=1024,
    )
    choice = response.choices[0]
    if not choice.message.content:
        return (
            "No explanation could be generated.",
            ["Response was empty."],
        )
    try:
        data = json.loads(choice.message.content)
        text = data.get("explanation_text", "").strip() or "No explanation generated."
        facts = data.get("supporting_facts", [])
        if not isinstance(facts, list):
            facts = [str(f) for f in facts] if facts else []
        else:
            facts = [str(f).strip() for f in facts if f]
        return (text, facts)
    except (json.JSONDecodeError, TypeError) as e:
        return (
            "The explanation could not be parsed.",
            [f"Parse error: {e!s}"],
        )
