# Backend Layer Contracts

Frozen interfaces between Core Simulation, Persistence, and API layers. All interactions must go through these explicit boundaries.

---

## Layer Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  API Layer (backend.api)                                             │
│  - Validates HTTP input                                              │
│  - Calls adapters + domain                                           │
│  - Returns JSON                                                      │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐     ┌─────────────────┐     ┌─────────────────────┐
│ Persistence   │     │ rankings_db     │     │ Simulation +        │
│ (users, teams,│     │ (players +      │     │ Scoring             │
│  matches)     │     │  ProfileStore   │     │ (pure domain)       │
└───────────────┘     │  adapter)       │     └─────────────────────┘
        │             └────────┬────────┘                ▲
        │                      │                         │
        │                      └─────────────────────────┘
        │                        ProfileStore in, PointEvents out
        │
        └──► SQLite (single DB: players + fantasy tables)
```

**Invariant:** Simulation and Scoring never import Persistence, rankings_db, or API. They receive data via function arguments and return data structures.

---

## 1. Core Simulation Layer

**Location:** `backend.simulation.*` (orchestrator, schemas, profiles, probability_engine, point_simulator, etc.)

**Dependencies:** None on DB, HTTP, AI, or external services.

### Inputs

| Function / Class | Input | Type |
|------------------|-------|------|
| `MatchOrchestrator(config, profile_store)` | `MatchConfig` | `match_id`, `player_a_id`, `player_b_id`, `seed`, `best_of` (default 5), `games_to_win_set` (default 11), `win_by` (default 2) |
| | `ProfileStore` | Must contain profiles for both `player_a_id` and `player_b_id` |

### Outputs

| Function | Output | Type |
|----------|--------|------|
| `orch.run()` | `Iterator[PointEvent]` | Yields one `PointEvent` per point until match completes |
| `sets_to_win_match(best_of)` | `int` | (best_of // 2) + 1 |

### PointEvent Contract

Each `PointEvent` has:

- `match_id`, `point_index`, `set_index`, `game_index`
- `score_before`, `score_after` (tuple[int, int] for current game)
- `set_scores_before`, `set_scores_after` (tuple[int, ...] for sets won)
- `outcome.winner_id`, `outcome.loser_id`, `outcome.shot_type`
- `rally_length`, `rally_category`
- `streak_broken`, `streak_continuing`, etc.

### Invariants

- Same `(player_a_id, player_b_id, seed)` ⇒ same sequence of `PointEvent`s (deterministic)
- No I/O, no randomness beyond `SeededRNG(seed)`

---

## 2. Scoring Layer

**Location:** `backend.scoring`

**Dependencies:** None on DB, HTTP, AI.

### Inputs

| Function | Input | Type |
|----------|-------|------|
| `aggregate_stats_from_events(events, winner_id, player_a_id, player_b_id, best_of)` | `events` | List of dict-like or `PointEvent` with `outcome.winner_id`, `outcome.shot_type`, `set_scores_after`, `score_before`, `score_after`, `set_index`, `streak_broken`, `streak_continuing` |
| | `winner_id` | Player who won the match |
| | `player_a_id`, `player_b_id` | Player IDs (must match events) |
| | `best_of` | 3 or 5 |
| `compute_fantasy_score(stats)` | `stats` | `MatchStats` |

### Outputs

| Function | Output | Type |
|----------|--------|------|
| `aggregate_stats_from_events(...)` | `tuple[MatchStats, MatchStats]` | Stats for player_a and player_b |
| `compute_fantasy_score(stats)` | `float` | Fantasy points |

### Invariants

- Scoring logic is pure; no side effects
- `events` can be `PointEvent` instances or dicts with the same structure (e.g. from `event_to_dict`)

---

## 3. Event Serialization (Simulation → Persistence Bridge)

**Location:** `backend.simulation.persistence.event_to_dict`

**Purpose:** Convert `PointEvent` to JSON-serializable dict for storage and replay.

| Function | Input | Output |
|----------|-------|--------|
| `event_to_dict(e: PointEvent)` | `PointEvent` | `dict` compatible with `aggregate_stats_from_events` and JSON serialization |

**Invariant:** Output dict must contain `outcome.winner_id`, `outcome.loser_id`, `outcome.shot_type`, `set_scores_after`, `score_before`, `score_after`, `set_index`, `streak_broken`, `streak_continuing` for scoring and replay.

---

## 4. Rankings DB (Players + Profile Adapter)

**Location:** `backend.rankings_db`

**Role:** Persistence for players (from rankings JSON) and adapter from `PlayerRow` → `ProfileStore`.

### Inputs

| Function | Input | Type |
|----------|-------|------|
| `get_player(conn, player_id)` | `conn` | `sqlite3.Connection` |
| | `player_id` | `str` |
| `list_players_by_gender(conn, gender, limit?)` | `gender` | `"men"` or `"women"` |
| `build_profile_store_for_match(conn, player_a_id, player_b_id, version?)` | `conn` | `sqlite3.Connection` |
| | `player_a_id`, `player_b_id` | Must exist in `players` table |

### Outputs

| Function | Output | Type |
|----------|--------|------|
| `get_player(...)` | `PlayerRow | None` | One row or None |
| `list_players_by_gender(...)` | `list[PlayerRow]` | Ordered by rank |
| `build_profile_store_for_match(...)` | `ProfileStore` | Contains profiles for both players |

### Invariants

- `build_profile_store_for_match` raises `ValueError` if either player is missing
- `ProfileStore` is consumed only by `MatchOrchestrator`; no persistence logic inside simulation

---

## 5. Persistence Layer (Fantasy Data)

**Location:** `backend.persistence.*`

**Dependencies:** `backend.models` (domain types). No dependency on simulation or scoring.

### Repositories

| Repository | Methods | Inputs | Outputs |
|------------|---------|--------|---------|
| `UserRepository` | `create`, `get`, `list_all` | `conn`, entity fields | `User` or `list[User]` |
| `TeamRepository` | `create`, `get`, `get_players`, `list_by_user` | `conn`, entity fields | `Team`, `list[str]` (player_ids), etc. |
| `MatchRepository` | `create`, `get`, `list_recent` | `conn`, entity fields | `Match` or `list[Match]` |

### Invariants

- All repository methods accept `conn: sqlite3.Connection` as first parameter (after `self`)
- No business logic: only CRUD
- `MatchRepository.create` accepts `events_json: str | None` (JSON string of serialized events)

---

## 6. API Layer

**Location:** `backend.api`

**Dependencies:** rankings_db, persistence, scoring, simulation (schemas, orchestrator). API orchestrates; it does not implement domain logic.

### Allowed Imports

- `backend.rankings_db`: `list_players_by_gender`, `get_player`, `build_profile_store_for_match`
- `backend.persistence`: `get_connection`, `init_db`, `UserRepository`, `TeamRepository`, `MatchRepository`
- `backend.analytics`: `compute_match_analytics` (deterministic analytics from match + events)
- `backend.explanation`: `explain_match`, `ExplainResponse` (read-only LLM explanation)
- `backend.explanation.llm`: `ExplanationUnavailableError`
- `backend.scoring`: `aggregate_stats_from_events`, `compute_fantasy_score`
- `backend.simulation.schemas`: `MatchConfig`
- `backend.simulation.orchestrator`: `MatchOrchestrator`, `sets_to_win_match`
- `backend.simulation.persistence`: `event_to_dict`

### Flow (POST /simulate/match)

1. Validate request; resolve team IDs to player IDs (first player per team)
2. `build_profile_store_for_match(conn, player_a_id, player_b_id)` → ProfileStore
3. `MatchOrchestrator(config, store).run()` → collect PointEvents
4. Derive `winner_id`, `sets_a`, `sets_b` from last event
5. `event_to_dict(e)` for each event → JSON → `events_json`
6. `MatchRepository.create(...)` with `events_json`
7. `aggregate_stats_from_events(...)` → fantasy scores
8. Return match + fantasy_scores

---

## 7. AI Access Boundaries

**Future AI integration must respect these boundaries.**

### ✅ AI MAY Read (Read-Only)

- `matches` table: `id`, `winner_id`, `sets_a`, `sets_b`, `player_a_id`, `player_b_id`, `events_json`, `seed`, `created_at`
- `players` table: `id`, `name`, `country`, `gender`, `rank`, `points` (for context)
- `teams` table: metadata only
- Deserialized `events_json` for match narration, analytics, or recaps

### ❌ AI MAY NOT

- Call or modify `MatchOrchestrator`, `PointSimulator`, `ProbabilityEngine`, or any simulation logic
- Call or modify `compute_fantasy_score`, `aggregate_stats_from_events`, or scoring constants
- Write to `players` table or change `ProfileStore` / `PlayerProfile` construction
- Inject prompts, models, or LLM calls into `backend.simulation` or `backend.scoring`

### Integration Pattern

AI features should:

1. Read match/event data via `MatchRepository.get()` or equivalent
2. Consume `events_json` and metadata as input to external AI services
3. Store AI outputs (e.g. recaps, recommendations) in separate tables or services
4. Never modify or bypass the simulation or scoring engines

### Implemented: Explanation Feature (backend.explanation)

- **GET /analysis/match/{id}**: Deterministic analytics (outcome, stats, fantasy_scores). No LLM.
- **POST /explain/match**: Read-only LLM explanation. Input: `match_id`, optional `user_query`. Output: `explanation_text`, `supporting_facts`.
- **LLM config**: Client is configurable via `OPENAI_API_KEY`. If unset (or `openai` not installed), the endpoint returns a **stub** response (200) so the API works end-to-end; no 503.
- **RAG pipeline**: Interpret query → decide retrievals → fetch match_summary, match_analytics, player_context, rules_context (from backend only) → assemble prompt → call LLM or stub → return validated response. All claims traceable to retrieved data.
- **Retrieval** (read-only): `get_match_analytics`, `get_match_summary`, `get_player_context`, `get_rules_context`. No simulation or write APIs.
- **AI boundaries**: Explanation never calls simulation or scoring; output is advisory; no fantasy team selection or autonomous agents.

---

## 8. Dependency Direction

```
API → rankings_db, persistence, analytics, explanation, scoring, simulation (schemas, orchestrator, persistence.event_to_dict)
explanation → analytics, persistence (read), rankings_db (read)
analytics → scoring, models (Match)
Persistence → models (only)
rankings_db → simulation.profiles (for ProfileStore, PlayerProfile; adapter only)
Simulation → (no external deps)
Scoring → (no external deps)
```

**Rule:** Core domain (simulation, scoring) has zero inbound dependencies from infrastructure.
