# Backend Design: Table Tennis Fantasy

**See [CONTRACTS.md](CONTRACTS.md) for frozen layer interfaces, inputs/outputs, invariants, and AI access boundaries.**

## Overview

The backend foundation separates:

- **Core domain** (simulation, scoring) — deterministic, no DB/API/AI
- **Persistence** — SQLite, CRUD only
- **API layer** — thin wrappers around domain + persistence

---

## Step 1: Data Models

### User

| Field     | Type   | Mutable | Description                |
|----------|--------|---------|----------------------------|
| id       | TEXT   | No      | Primary key (UUID)         |
| name     | TEXT   | Yes     | Display name               |
| created_at | TEXT | No      | ISO datetime               |

**Purpose:** Placeholder for fantasy app users. Auth is not implemented.

### Player

Players live in `rankings_db.players` (rankings + simulation stats). Referenced by `id` in teams and matches. No separate ORM model; use `PlayerRow` when reading from DB.

### Team

| Field     | Type   | Mutable | Description                |
|----------|--------|---------|----------------------------|
| id       | TEXT   | No      | Primary key (UUID)         |
| user_id  | TEXT   | No      | FK → users                 |
| name     | TEXT   | Yes     | Team name                  |
| created_at | TEXT | No      | ISO datetime               |

### TeamPlayer (many-to-many)

| Field    | Type  | Mutable | Description                      |
|----------|-------|---------|----------------------------------|
| team_id  | TEXT  | No      | FK → teams (part of PK)         |
| player_id| TEXT  | No      | FK → players (part of PK)       |
| position | INT   | Yes     | 1-based roster order            |

**Relationships:** Composite PK `(team_id, player_id)` enforces uniqueness. Indexes on both FKs for lookups.

### Match

| Field       | Type   | Mutable | Description                           |
|-------------|--------|---------|---------------------------------------|
| id          | TEXT   | No      | Primary key (e.g. sim-{teams}-{seed}) |
| team_a_id   | TEXT   | No      | FK → teams                            |
| team_b_id   | TEXT   | No      | FK → teams                            |
| player_a_id | TEXT   | No      | Actual player who competed (team A)   |
| player_b_id | TEXT   | No      | Actual player who competed (team B)   |
| winner_id   | TEXT   | No      | player_id who won                     |
| sets_a      | INT    | No      | Sets won by team A                    |
| sets_b      | INT    | No      | Sets won by team B                    |
| best_of     | INT    | No      | 3 or 5                                |
| seed        | INT    | No      | RNG seed for reproducibility          |
| created_at  | TEXT   | No      | ISO datetime                          |
| events_json | TEXT   | No      | Optional serialized point events      |

**Design note:** A match is between two *teams*, but the simulation runs on two *players*. We use the first player (by position) from each team. This keeps the slice simple; later you can add "starter" selection.

---

## Step 2: Persistence Layer

### File Structure

```
backend/
  persistence/
    __init__.py
    schema.py      # DDL for users, teams, team_players, matches
    db.py          # get_connection, init_db
    repositories.py# UserRepository, TeamRepository, MatchRepository
```

### Schema

- `IF NOT EXISTS` on all tables for migration-friendly creation
- Foreign keys defined (SQLite does not enforce by default; can enable with `PRAGMA foreign_keys=ON`)
- Indexes on team_players(team_id), team_players(player_id), matches(team_a_id), matches(team_b_id), matches(created_at)

### Repositories

- **UserRepository:** `create`, `get`, `list_all`
- **TeamRepository:** `create`, `get`, `get_players`, `list_by_user`
- **MatchRepository:** `create`, `get`, `list_recent`

No business logic in repositories — only read/write.

---

## Step 3: API Design

### Endpoints

| Method | Path                | Description                                      |
|--------|---------------------|--------------------------------------------------|
| GET    | /players            | List players (optional gender filter)            |
| POST   | /teams              | Create team                                      |
| GET    | /teams/{id}         | Get team with players                            |
| POST   | /simulate/match     | Simulate match, persist, return                  |
| GET    | /matches/{id}       | Get match by ID                                  |
| GET    | /analysis/match/{id}| Deterministic analytics (stats, outcome, fantasy) |
| POST   | /explain/match      | LLM explanation (match_id, optional user_query)  |

### Example Payloads

**POST /teams**
```json
// Request
{
  "user_id": "user-123",
  "name": "Team Alpha",
  "player_ids": ["wang_chuqin", "lin_shidong", "hugo_calderano"]
}

// Response 200
{
  "id": "uuid",
  "user_id": "user-123",
  "name": "Team Alpha",
  "player_ids": ["wang_chuqin", "lin_shidong", "hugo_calderano"],
  "created_at": "2025-02-04T12:00:00"
}
```

**POST /simulate/match**
```json
// Request
{
  "team_a_id": "uuid-a",
  "team_b_id": "uuid-b",
  "seed": 42,
  "best_of": 5
}

// Response 200
{
  "id": "sim-uuid-a-uuid-b-42",
  "team_a_id": "uuid-a",
  "team_b_id": "uuid-b",
  "player_a_id": "wang_chuqin",
  "player_b_id": "lin_shidong",
  "winner_id": "wang_chuqin",
  "sets_a": 3,
  "sets_b": 2,
  "best_of": 5,
  "seed": 42,
  "created_at": "...",
  "fantasy_scores": { "wang_chuqin": 56.5, "lin_shidong": 36.5 }
}
```

### Error Handling

- 400: Invalid input (e.g. unknown player_id, empty team)
- 404: Team or match not found
- 500: Simulation or persistence failure

---

## Step 4: Vertical Slice

**Flow:**
1. Create user (auto-created if missing)
2. Create team A with players
3. Create team B with players
4. Simulate match (first player per team)
5. Persist match result + events
6. Retrieve match by ID

**Run:**
```bash
python3 scripts/vertical_slice.py
```

**API test** (requires `pip install httpx`):
```bash
uvicorn backend.api:app --reload
# In another terminal:
curl http://127.0.0.1:8000/players?gender=men
```

---

## Future Compatibility

- **AI analytics:** Match data (events_json, winner, sets) is persisted; AI can read without touching simulation.
- **AI recaps:** Same — events are stored for replay/narration.
- **Explanation feature (implemented):** `GET /analysis/match/{id}` returns deterministic analytics; `POST /explain/match` uses an agentic RAG pipeline (retrieval → prompt → LLM) to produce read-only explanations. Requires `OPENAI_API_KEY`. See CONTRACTS.md §7.
- **Postgres:** Schema uses standard SQL; repositories use parameterized queries. Swap connection + init for Postgres driver.

---

## Running the API

```bash
# From project root
uvicorn backend.api:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI docs: http://127.0.0.1:8000/docs

---

## Try the LLM explanation feature

**Option A — Script (easiest)**

```bash
# Terminal 1: start the API
export OPENAI_API_KEY=sk-your-key-here
uvicorn backend.api:app --reload --port 8000

# Terminal 2: create a match and get analytics + LLM explanation
python3 scripts/try_explain.py
```

The script creates two teams, simulates a match, prints `GET /analysis/match/{id}` (deterministic analytics), then `POST /explain/match` (LLM summary). Without `OPENAI_API_KEY`, the explain call returns 503 and the script exits cleanly.

**Option B — curl**

With the API already running:

```bash
# Create teams (save the "id" from each response), then simulate:
curl -s -X POST http://127.0.0.1:8000/simulate/match -H "Content-Type: application/json" \
  -d '{"team_a_id":"<TEAM_A_ID>","team_b_id":"<TEAM_B_ID>","seed":42,"best_of":5}' -o /tmp/match.json

MATCH_ID=$(python3 -c "import json; print(json.load(open('/tmp/match.json'))['id'])")

# Deterministic analytics (no API key)
curl -s "http://127.0.0.1:8000/analysis/match/$MATCH_ID" | python3 -m json.tool

# LLM explanation (requires OPENAI_API_KEY)
curl -s -X POST http://127.0.0.1:8000/explain/match -H "Content-Type: application/json" \
  -d "{\"match_id\": \"$MATCH_ID\", \"user_query\": \"Why did the winner win?\"}" | python3 -m json.tool
```
