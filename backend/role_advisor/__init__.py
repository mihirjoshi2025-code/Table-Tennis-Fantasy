"""
Role advisory agent: read-only AI that recommends which players suit which roles.

Why advice ≠ automation: The agent returns recommendations and explanations only.
The user makes the final role assignment. The agent never mutates team or roster state.

Role mechanics are validated in backend/tests/test_role_scoring.py (deterministic
scoring, role-specific effects, regression, explainability).
"""
from __future__ import annotations

from backend.role_advisor.orchestration import advise_roles
from backend.role_advisor.schemas import RoleAdvisorResponse, RoleRecommendation

__all__ = ["advise_roles", "RoleAdvisorResponse"]
