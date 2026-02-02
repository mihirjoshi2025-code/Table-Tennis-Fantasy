"""
Player Profile Store: per-player probability profiles from historical data.
Versioned and auditable; used by the Probability Engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import json
from pathlib import Path


@dataclass
class PlayerProfile:
    """
    Probability profile for one player.
    Derived from aggregated historical data; parameters can be
    parametric (e.g. Beta) or stored as raw stats.
    """
    player_id: str
    version: str
    # Baseline chance to win a point in neutral context (vs average opponent)
    baseline_point_win: float  # 0..1
    # Serve advantage: multiplier when this player is serving
    serve_multiplier: float  # e.g. 1.05
    # Error rate curve: (rally_length) -> extra error probability
    # Stored as (length_bucket, rate) or fitted params
    error_curve: dict[str, Any] = field(default_factory=dict)
    # Small boost when on a streak (probability continuation)
    streak_bias: float = 0.02  # additive to win prob when on 3+ streak
    # Clutch: boost in pressure situations (deciding set, close score)
    clutch_modifier: float = 0.03
    # Rally length distribution: weights for short/medium/long
    rally_length_dist: tuple[float, float, float] = (0.4, 0.4, 0.2)
    # How much fatigue affects this player (0 = no effect, 1 = full)
    fatigue_sensitivity: float = 0.5
    # Style: fraction of winners that are forehand / backhand / service
    style_mix: tuple[float, float, float] = (0.45, 0.35, 0.2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "version": self.version,
            "baseline_point_win": self.baseline_point_win,
            "serve_multiplier": self.serve_multiplier,
            "error_curve": self.error_curve,
            "streak_bias": self.streak_bias,
            "clutch_modifier": self.clutch_modifier,
            "rally_length_dist": list(self.rally_length_dist),
            "fatigue_sensitivity": self.fatigue_sensitivity,
            "style_mix": list(self.style_mix),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlayerProfile:
        return cls(
            player_id=d["player_id"],
            version=d["version"],
            baseline_point_win=d["baseline_point_win"],
            serve_multiplier=d["serve_multiplier"],
            error_curve=d.get("error_curve", {}),
            streak_bias=d.get("streak_bias", 0.02),
            clutch_modifier=d.get("clutch_modifier", 0.03),
            rally_length_dist=tuple(d.get("rally_length_dist", [0.4, 0.4, 0.2])),
            fatigue_sensitivity=d.get("fatigue_sensitivity", 0.5),
            style_mix=tuple(d.get("style_mix", [0.45, 0.35, 0.2])),
        )


class ProfileStore:
    """
    Holds and retrieves player profiles.
    Can load from JSON files or in-memory dict; versioned for audit.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, PlayerProfile] = {}

    def get(self, player_id: str) -> PlayerProfile | None:
        return self._profiles.get(player_id)

    def put(self, profile: PlayerProfile) -> None:
        self._profiles[profile.player_id] = profile

    def load_from_dir(self, directory: str | Path) -> None:
        path = Path(directory)
        for f in path.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if "player_id" in data:
                    self.put(PlayerProfile.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue

    def save_profile(self, profile: PlayerProfile, directory: str | Path) -> Path:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        filepath = path / f"{profile.player_id}_{profile.version}.json"
        filepath.write_text(json.dumps(profile.to_dict(), indent=2))
        return filepath


def default_profile(player_id: str, version: str = "v1", elo_advantage: float = 0.0) -> PlayerProfile:
    """
    Build a default profile for testing/demos.
    elo_advantage: small offset to baseline_point_win (e.g. 0.05 for stronger).
    """
    base = 0.5 + max(-0.2, min(0.2, elo_advantage))
    return PlayerProfile(
        player_id=player_id,
        version=version,
        baseline_point_win=base,
        serve_multiplier=1.04,
        error_curve={"short": 0.02, "medium": 0.04, "long": 0.08},
        streak_bias=0.02,
        clutch_modifier=0.03,
        rally_length_dist=(0.4, 0.4, 0.2),
        fatigue_sensitivity=0.5,
        style_mix=(0.45, 0.35, 0.2),
    )
