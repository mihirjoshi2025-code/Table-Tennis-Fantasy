"""
Schemas for the explanation feature.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextBundle:
    """Assembled context for the LLM. Sources used are explicit and traceable."""
    match_summary: dict[str, Any] | None = None
    match_analytics: dict[str, Any] | None = None
    player_context: list[dict[str, Any]] = field(default_factory=list)
    rules_context: str | None = None
    sources_used: list[str] = field(default_factory=list)


@dataclass
class ExplainResponse:
    """Response from the explanation endpoint."""
    explanation_text: str
    supporting_facts: list[str]
