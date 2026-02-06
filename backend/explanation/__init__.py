"""
Read-only LLM explanation feature.
Uses deterministic analytics and match data as grounding; never modifies
simulation, scoring, or persistence.
"""
from __future__ import annotations

from backend.explanation.orchestration import explain_match
from backend.explanation.schemas import ExplainResponse

__all__ = ["explain_match", "ExplainResponse"]
