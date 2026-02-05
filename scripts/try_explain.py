#!/usr/bin/env python3
"""
Call the API to create a match and get an LLM explanation.
Run with the API already up: uvicorn backend.api:app --reload --port 8000

  export OPENAI_API_KEY=your-openai-api-key-here
  python3 scripts/try_explain.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx", file=sys.stderr)
    sys.exit(1)

BASE = "http://127.0.0.1:8000"


def main() -> None:
    client = httpx.Client(timeout=30.0)
    try:
        # Get players
        r = client.get(f"{BASE}/players", params={"gender": "men", "limit": 4})
        r.raise_for_status()
        players = r.json()["players"]
        ids = [p["id"] for p in players[:4]]
        print(f"Using players: {[p['name'] for p in players[:4]]}")

        # Create two teams
        t1 = client.post(f"{BASE}/teams", json={"user_id": "demo", "name": "Team A", "gender": "men", "player_ids": ids[:2]})
        t2 = client.post(f"{BASE}/teams", json={"user_id": "demo", "name": "Team B", "gender": "men", "player_ids": ids[2:4]})
        t1.raise_for_status()
        t2.raise_for_status()
        team_a_id = t1.json()["id"]
        team_b_id = t2.json()["id"]
        print(f"Created teams: {team_a_id[:8]}..., {team_b_id[:8]}...")

        # Simulate match
        sim = client.post(
            f"{BASE}/simulate/match",
            json={"team_a_id": team_a_id, "team_b_id": team_b_id, "seed": 42, "best_of": 5},
        )
        sim.raise_for_status()
        match = sim.json()
        match_id = match["id"]
        print(f"Match: {match_id}")
        print(f"  Result: {match['sets_a']}-{match['sets_b']} (winner: {match['winner_id']})")

        # Deterministic analytics (no LLM)
        anal = client.get(f"{BASE}/analysis/match/{match_id}")
        anal.raise_for_status()
        print("\n--- Analytics (GET /analysis/match/{id}) ---")
        print(json.dumps(anal.json(), indent=2)[:800] + "...\n")

        # LLM explanation (or stub if OPENAI_API_KEY not set)
        explain = client.post(
            f"{BASE}/explain/match",
            json={"match_id": match_id, "user_query": "Why did the winner win?"},
        )
        if explain.status_code != 200:
            try:
                err = explain.json()
                print("Server error response:", err)
            except Exception:
                print("Server error body:", explain.text[:500])
        explain.raise_for_status()
        out = explain.json()
        print("--- LLM explanation (POST /explain/match) ---")
        print("explanation_text:", out.get("explanation_text", ""))
        print("supporting_facts:", out.get("supporting_facts", []))
        if "OPENAI_API_KEY" in out.get("explanation_text", ""):
            print("  (Stub: set OPENAI_API_KEY in the server terminal to enable real LLM explanations.)")
    finally:
        client.close()


if __name__ == "__main__":
    main()
