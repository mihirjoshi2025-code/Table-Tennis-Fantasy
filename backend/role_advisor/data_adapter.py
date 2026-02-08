"""
Data adapter for the role advisory agent. Read-only; no writes.

Exposes player statistics the agent uses to recommend roles.
Stats we have: rank, points, salary, clutch_modifier, streak_bias, fatigue_sensitivity.
Stats we do not have (documented below): average points per game, variance, late-game strength,
momentum sensitivity, upset rate — we infer conservatively or omit.
"""
from __future__ import annotations

from typing import Any

from backend.rankings_db import get_player


# ---------- Assumptions when a stat does not exist ----------
# CONSISTENCY / VARIANCE: We do not store historical fantasy points per game per player.
#   Inference: use rank tier as a conservative proxy (top rank → assumed more consistent).
# LATE-GAME STRENGTH: We use clutch_modifier from the simulation profile as a proxy.
# MOMENTUM SENSITIVITY: We use streak_bias and fatigue_sensitivity as proxies.
# UPSET RATE vs stronger opponents: Not stored; not used in scoring. Document only.


def get_player_stats_for_advisor(conn: Any, player_ids: list[str]) -> list[dict[str, Any]]:
    """
    Return structured player stats for the advisor. Read-only.
    Missing stats are inferred conservatively and documented in the returned structure.
    """
    out: list[dict[str, Any]] = []
    for pid in player_ids:
        row = get_player(conn, pid)
        if row is None:
            continue
        # Consistency proxy: we have no historical variance; assume higher rank = more consistent.
        # Rank 1–10: low variance proxy 0.8; 11–30: 0.6; 31–50: 0.5; 51+: 0.4 (more variance assumed).
        rank = getattr(row, "rank", 50)
        if rank <= 10:
            consistency_proxy = 0.8
        elif rank <= 30:
            consistency_proxy = 0.6
        elif rank <= 50:
            consistency_proxy = 0.5
        else:
            consistency_proxy = 0.4
        # Explicit tier for diverse recommendations: top 10, 11-20, 21+
        if rank <= 10:
            rank_tier = "1-10"
        elif rank <= 20:
            rank_tier = "11-20"
        else:
            rank_tier = "21+"
        out.append({
            "id": row.id,
            "name": row.name,
            "country": row.country,
            "gender": row.gender,
            "rank": rank,
            "rank_tier": rank_tier,
            "points": getattr(row, "points", 0),
            "salary": getattr(row, "salary", 100),
            "clutch_modifier": getattr(row, "clutch_modifier", 0.03),
            "streak_bias": getattr(row, "streak_bias", 0.02),
            "fatigue_sensitivity": getattr(row, "fatigue_sensitivity", 0.5),
            "consistency_proxy": consistency_proxy,
            "_assumptions": "consistency_proxy from rank tier (no historical variance stored); clutch/streak/fatigue from simulation profile.",
        })
    return out
