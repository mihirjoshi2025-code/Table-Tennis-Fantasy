"""
Strategic player roles that modify scoring behavior.
Roles are evaluated via this handler layer so core simulation loops stay free of role-specific logic.
Each team may assign at most one player per role; roles only apply to active players (slots 1-7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------- Role enum (exactly these 5) ----------


class Role(str, Enum):
    ANCHOR = "anchor"
    AGGRESSOR = "aggressor"
    CLOSER = "closer"
    WILDCARD = "wildcard"
    STABILIZER = "stabilizer"


# ---------- Role definitions (shown to users) ----------
# Descriptions and modifiers live here so we can add new roles or tweak without touching simulation.


@dataclass(frozen=True)
class RoleDefinition:
    name: str
    description: str
    # Scoring modifiers are applied in apply_role_to_fantasy_score; this is for display only.
    modifier_summary: str


ROLE_DEFINITIONS: dict[Role, RoleDefinition] = {
    Role.ANCHOR: RoleDefinition(
        name="Anchor",
        description="Lower variance in scoring. +10% consistency. Reduced penalty on losses.",
        modifier_summary="+10% consistency; reduced loss penalty",
    ),
    Role.AGGRESSOR: RoleDefinition(
        name="Aggressor",
        description="+25% upside on positive scoring events. −15% downside on negative scoring events. Higher volatility.",
        modifier_summary="+25% on gains, −15% on losses (higher volatility)",
    ),
    Role.CLOSER: RoleDefinition(
        name="Closer",
        description="Bonus points in final game(s) of a match. No effect early in the match.",
        modifier_summary="Bonus in final 1–2 games only",
    ),
    Role.WILDCARD: RoleDefinition(
        name="Wildcard",
        description="Random event-based bonuses. Higher variance than all other roles. Effects trigger unpredictably but fairly.",
        modifier_summary="Random rate-limited bonus; never dominates",
    ),
    Role.STABILIZER: RoleDefinition(
        name="Stabilizer",
        description="Prevents or dampens team-wide momentum drops. Reduces negative momentum cascades.",
        modifier_summary="Dampens negative score impact",
    ),
}


def get_role_definition(role: Role) -> RoleDefinition:
    return ROLE_DEFINITIONS[role]


def list_all_roles() -> list[tuple[Role, RoleDefinition]]:
    """For API/frontend: list all roles with definitions."""
    return [(r, ROLE_DEFINITIONS[r]) for r in Role]


# ---------- Role context (input to handler) ----------
# So we don't hardcode slot/game logic inside simulation; handler receives context.


@dataclass
class RoleContext:
    """Context for applying a role. Passed from simulation_service so roles stay composable."""
    slot_index: int       # 0-based game index (0..6)
    total_slots: int      # 7
    is_winner: bool      # this player won the head-to-head
    team_side: str       # "home" | "away"
    cumulative_team_score_before: float  # team total before this slot (for stabilizer / momentum)
    seed: int            # for deterministic Wildcard


# ---------- Role event log (every role-triggered effect) ----------


@dataclass
class RoleLogEntry:
    """One role-triggered effect for debugging and live summaries."""
    player_id: str
    role: str
    game_slot: int       # 1-based
    description: str
    raw_score: float
    adjusted_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "role": self.role,
            "game_slot": self.game_slot,
            "description": self.description,
            "raw_score": round(self.raw_score, 2),
            "adjusted_score": round(self.adjusted_score, 2),
        }


# ---------- Role handler (single place for all role logic) ----------
# Why: Keeps simulation loop clean; new roles or stacking can be added here without touching scoring.py.


def apply_role_to_fantasy_score(
    raw_score: float,
    player_id: str,
    role: Role | None,
    ctx: RoleContext,
) -> tuple[float, list[RoleLogEntry]]:
    """
    Apply role modifier to raw fantasy score. Returns (adjusted_score, log_entries).
    If role is None, returns (raw_score, []). All role logic is here so simulation stays role-agnostic.
    """
    if role is None:
        return (raw_score, [])

    log_entries: list[RoleLogEntry] = []
    game_slot_1based = ctx.slot_index + 1

    if role == Role.ANCHOR:
        # +10% consistency: scale positive scores up slightly; reduced penalty on losses (soften negative).
        if raw_score >= 0:
            adjusted = raw_score * 1.10
        else:
            adjusted = raw_score * 0.70  # reduce magnitude of loss penalty
        log_entries.append(RoleLogEntry(
            player_id=player_id,
            role=role.value,
            game_slot=game_slot_1based,
            description="Anchor: consistency applied",
            raw_score=raw_score,
            adjusted_score=adjusted,
        ))
        return (adjusted, log_entries)

    if role == Role.AGGRESSOR:
        # +25% upside on positive, −15% downside on negative (multiply negative by 1.15 so more negative).
        if raw_score >= 0:
            adjusted = raw_score * 1.25
        else:
            adjusted = raw_score * 1.15
        log_entries.append(RoleLogEntry(
            player_id=player_id,
            role=role.value,
            game_slot=game_slot_1based,
            description="Aggressor bonus applied" if raw_score >= 0 else "Aggressor downside applied",
            raw_score=raw_score,
            adjusted_score=adjusted,
        ))
        return (adjusted, log_entries)

    if role == Role.CLOSER:
        # Bonus only in final 1–2 games (slot_index 5 or 6 in 0-based, i.e. games 6 and 7).
        is_final_game = ctx.slot_index >= ctx.total_slots - 2
        if is_final_game:
            adjusted = raw_score * 1.20  # 20% bonus in closing games
            log_entries.append(RoleLogEntry(
                player_id=player_id,
                role=role.value,
                game_slot=game_slot_1based,
                description="Closer bonus applied (final game)",
                raw_score=raw_score,
                adjusted_score=adjusted,
            ))
            return (adjusted, log_entries)
        return (raw_score, [])

    if role == Role.WILDCARD:
        # Rate-limited random bonus. Deterministic from seed so replay is consistent.
        # Trigger ~15% of the time; cap bonus so it never dominates (e.g. +1.5 max, or 15% of |raw|).
        rng = (ctx.seed + ctx.slot_index * 31 + sum(ord(c) for c in player_id) % 1000) % 100
        if rng < 15:
            bonus = min(1.5, max(0.3, abs(raw_score) * 0.15))  # 15% of magnitude, clamped
            adjusted = raw_score + bonus
            log_entries.append(RoleLogEntry(
                player_id=player_id,
                role=role.value,
                game_slot=game_slot_1based,
                description="Wildcard bonus triggered",
                raw_score=raw_score,
                adjusted_score=adjusted,
            ))
            return (adjusted, log_entries)
        return (raw_score, [])

    if role == Role.STABILIZER:
        # Dampen negative momentum: when this player's score is negative, reduce magnitude.
        # Implemented at player level (this player's negative impact is softened) to avoid
        # requiring full team state in the handler; effect still "reduces negative cascades".
        if raw_score < 0:
            adjusted = raw_score * 0.60  # 40% dampening of negative
            log_entries.append(RoleLogEntry(
                player_id=player_id,
                role=role.value,
                game_slot=game_slot_1based,
                description="Stabilizer prevented momentum drop",
                raw_score=raw_score,
                adjusted_score=adjusted,
            ))
            return (adjusted, log_entries)
        return (raw_score, [])

    return (raw_score, [])


def parse_role(value: str | None) -> Role | None:
    """Parse role string to enum; None if invalid or empty."""
    if not value:
        return None
    try:
        return Role(value.strip().lower())
    except ValueError:
        return None
