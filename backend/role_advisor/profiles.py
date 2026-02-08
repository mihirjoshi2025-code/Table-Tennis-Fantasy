"""
Role profiles: explicit intent for each role (not numbers).

Used by the advisory agent to match player stats to role requirements.
Scoring mechanics live in backend.roles; this module is advisory context only.
"""
from __future__ import annotations

# ---------- Role intent (hardcoded for agent context) ----------
# Advice ≠ automation: these describe what each role rewards so the LLM can recommend fit.
# Numbers (multipliers, thresholds) are in backend.roles.apply_role_to_fantasy_score.

ROLE_PROFILES = """
## Role profiles (intent only; scoring is in the simulation)

- **Anchor**: Low variance, consistency, loss mitigation. Best for players who perform steadily and absorb losses without big swings. High variance or volatility is a poor fit.

- **Aggressor**: High upside, risk-reward. Best for players who swing big—strong upside on good games, worse downside on bad ones. Avoid for players you need to be reliable.

- **Closer**: Late-game impact. Best for players you want in the final games of a match. No effect early; bonus only in the last 1–2 games. Fit players who thrive under pressure or have strong clutch stats.

- **Wildcard**: Unpredictable, swing potential. Random bonuses; higher variance. Best for diversifying variance, not for anchoring a strategy. Rate-limited and logged.

- **Stabilizer**: Momentum control. Reduces negative momentum cascades. Best for players who can dampen bad runs. No effect when the player scores positively.
"""

# Single-line summaries for compact context
ROLE_SUMMARIES = {
    "anchor": "low variance, consistency, reduced loss penalty",
    "aggressor": "high upside and downside, risk-reward",
    "closer": "bonus only in final 1–2 games",
    "wildcard": "random rate-limited bonus, high variance",
    "stabilizer": "dampens negative score impact",
}
