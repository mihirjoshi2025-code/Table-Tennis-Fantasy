"""
Prompt for the role advisory agent.

Instructions: advise only; never auto-assign. Use real stats and role profiles.
"""
from __future__ import annotations

import json
from typing import Any

from backend.role_advisor.profiles import ROLE_PROFILES


SYSTEM_INSTRUCTION = """You are a table tennis fantasy coach. Your role is to advise which players suit which roles. You do NOT modify team data, auto-assign roles, or override constraints.

Rules:
- Base every recommendation on the provided player stats and role profiles. Use rank_tier (1-10, 11-20, 21+) to give flexible options across different rank/budget tiers.
- When the user asks for a good player for a specific role (e.g. "who should I assign as Aggressor?" or "best Anchor?"), recommend exactly three options when possible: (1) one player from rank_tier "1-10" whose stats fit the role best, (2) one from "11-20", and (3) one from "21+". Match stats to the role—e.g. Anchor needs consistency/low variance; Aggressor needs upside; Closer benefits from clutch; Stabilizer from dampening—do NOT just pick the top-ranked players.
- Explain why each player fits the role and state one downside or risk per pick.
- If the user asks "is Player X better as A or B?", compare and recommend one, with tradeoffs.
- If data is insufficient (e.g. no players in context), say so. Do not invent stats.
- Output must be advisory only. The user makes the final assignment."""


def build_advisor_prompt(
    player_stats: list[dict[str, Any]],
    role_profiles: str,
    user_query: str,
) -> list[dict[str, str]]:
    """
    Build the message list for the LLM: system + user with player stats, role profiles, and query.
    """
    stats_block = json.dumps(player_stats, indent=2)
    user_content = f"""Use only the following data. Do not invent stats.

## Player statistics (from data adapter)
{stats_block}

## Role profiles (intent; scoring mechanics are in the simulation)
{role_profiles}

---

User question: {user_query}

Respond with:
1. recommendations: list of {{ "player_id", "player_name", "suggested_role", "why_fit", "risk" }}. When suggesting players for a role, give one from rank_tier 1-10, one from 11-20, and one from 21+ when possible (so the user has options at different salary/rank levels). Order: tier 1-10 first, then 11-20, then 21+.
2. explanation: short natural-language summary (e.g. "One elite option, one mid-tier, one value pick.")
3. tradeoffs: string with key tradeoffs or risks (use empty string if none).

If no players are in context or the question cannot be answered from the data, return empty recommendations and explain why."""
    return [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": user_content},
    ]
