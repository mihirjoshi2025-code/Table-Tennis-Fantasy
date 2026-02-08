"""
Schemas for the role advisory agent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RoleRecommendation:
    """One recommendation: player + suggested role + why + risk."""
    player_id: str
    player_name: str
    suggested_role: str
    why_fit: str
    risk: str


@dataclass
class RoleAdvisorResponse:
    """Response from the role advisor endpoint. Advisory only; no state change."""
    recommendations: list[RoleRecommendation]
    explanation: str
    tradeoffs: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendations": [
                {
                    "player_id": r.player_id,
                    "player_name": r.player_name,
                    "suggested_role": r.suggested_role,
                    "why_fit": r.why_fit,
                    "risk": r.risk,
                }
                for r in self.recommendations
            ],
            "explanation": self.explanation,
            "tradeoffs": self.tradeoffs,
        }
