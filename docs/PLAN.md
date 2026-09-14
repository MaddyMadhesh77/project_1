# RecoverMem — Build Plan

Status: Draft v1 · 2026-07-28
Companion to [DESIGN.md](DESIGN.md) — this document turns §11's phase list
into concrete, checkable tasks. Design decisions are not repeated here;
where a task implements a specific mechanism, it links back to the
DESIGN.md section (e.g. "§6.5") rather than re-describing it.

Ground rule from CLAUDE.md: **every phase must leave the demo runnable.**
No phase should end with the app in a broken or half-wired state — if a
task can't be finished in one sitting, land it behind a no-op default
rather than leaving the pipeline unable to run.

---

## 0. Pre-flight: Open Questions (DESIGN.md §12)

These block specific phases, not the whole plan. Proposed defaults below
let work start now; flagged items should be confirmed with the user before
the phase that needs them, not silently locked in.

| # | Question | Proposed default | Confirm before |
|---|---|---|---|
| 1 | LLM provider for chat + extraction fallback | Ship the `LLMClient` interface (§10) with **two** implementations from the start: a `TemplatedLLMClient` (canned/rule-based replies, zero API key, fully deterministic — good for rehearsed demos) and a `ClaudeLLMClient` (Anthropic API, since this is a Claude Code project and the pitch's "ChatGPT" framing is cosmetic). Default to `TemplatedLLMClient` unless `ANTHROPIC_API_KEY` is set. | Phase 1 |
| 2 | Where the guide runs the demo | Local laptop only (`docker-compose` + `npm run dev`). No deployment target for MVP. | Phase 0 (affects whether CORS/env need to handle a public origin) |
| 3 | RF bootstrap dataset | Hand-authored, checked into repo at `backend/app/ml/data/synthetic_examples.json` (reproducible demo, diffable, reviewable) rather than generated fresh each run. | Phase 7 |
| 4 | Branding / palette | Use the `dataviz` / `artifact-design` skill's default neutral palette. No existing brand constraints. | Phase 3 (first UI with real charts/colors) |

---

## 1. Target Repo Layout

```
project-1/
  docker-compose.yml
  .env.example
  backend/
    pyproject.toml
    alembic.ini
    alembic/
      versions/
    app/
      main.py
      core/
        config.py            # pydantic-settings
        logging.py
      db/
        session.py            # async SQLAlchemy engine/session
        base.py
      models/                 # SQLAlchemy ORM, one file per table in §5
        memory.py
        memory_version.py
        provenance.py
        dependency_edge.py
        merkle_root.py
        trust_event.py
        rollback_event.py
      schemas/                 # Pydantic request/response models
      api/
        routes/
          chat.py
          memories.py
          trust.py
          integrity.py
          rollback.py
          attack.py
          search.py
          analytics.py
          logs.py
        deps.py
      services/
        llm_client.py          # LLMClient interface + Templated/Claude impls
        extractor.py            # Extractor interface + rule-based impl (§6.1)
        embedding.py             # EmbeddingService (§6.2)
        retrieval.py             # hybrid retrieval (§6.3)
        features.py              # feature engineering (§6.4)
        trust_engine.py          # rule scorer + RF/SHAP blend (§6.5)
        versioning.py            # §6.6
        merkle.py                # §6.8
        graph.py                 # networkx wrapper (§6.9)
        rollback.py              # §6.10
      ml/
        data/synthetic_examples.json
        train.py
        model.pkl               # generated artifact, gitignored
    tests/
      unit/
      integration/
    scripts/
      seed_demo.py               # pre-seeds the §9 demo-flow-2 chain
  frontend/
    package.json
    src/
      pages/            # exactly the list in DESIGN.md §8
      components/
      lib/
        api.ts
        queries.ts
      main.tsx
      App.tsx            # router: "/" chat, "/admin/*" dashboard
```

---

## 2. Phase-by-Phase Tasks

Each phase lists: goal, tasks, new/changed files, and a **demo checkpoint**
— the concrete thing you should be able to show at the end of the phase.
Phases are sequential; later phases assume earlier ones are done.

### Phase 0 — Repo Scaffold

**Goal:** empty-but-running skeleton, nothing security-related yet.

- [x] `git init`, `.gitignore` (Python, Node, `.env`, `*.pkl`, `alembic` cache)
- [x] `docker-compose.yml`: single `postgres` service on a pgvector-enabled
      image (e.g. `pgvector/pgvector:pg15`), named volume, exposed port,
      env vars sourced from `.env`
- [x] `.env.example` with `DATABASE_URL`, `ANTHROPIC_API_KEY` (optional),
      `EMBEDDING_MODEL`, `TRUST_THRESHOLDS`
- [x] Backend: `pyproject.toml` with FastAPI, SQLAlchemy 2.x (async),
      asyncpg, Alembic, pydantic-settings, sentence-transformers,
      scikit-learn, shap, networkx, pgvector-python
- [x] `app/main.py` — FastAPI app factory, CORS, one `GET /health` route
- [x] `app/core/config.py` — `Settings(BaseSettings)` reading `.env`
- [x] `app/db/session.py` — async engine + session factory
- [x] `alembic init`, point `env.py` at `Settings.database_url` and the
      (still-empty) SQLAlchemy metadata
- [x] Frontend: `npm create vite@latest frontend -- --template react-ts`,
      Tailwind installed and configured, React Router with two stub routes
      (`/` renders "Chat placeholder", `/admin/*` renders "Dashboard
      placeholder")
- [x] Root `README.md` updated with local run instructions (`docker-compose
      up -d`, `uvicorn app.main:app --reload`, `npm run dev`)

**Demo checkpoint:** `docker-compose up -d` starts Postgres; backend
`/health` returns 200; frontend loads both stub routes in a browser.
**Verified 2026-07-28.**

**Deviation from proposed default (§0 open question #2):** default Postgres
host port changed from 5432 to **5433** (`.env` / `docker-compose.yml`)
because this dev machine already runs a native Postgres service on 5432,
which was silently intercepting the container's connections. Not a design
change, just a local-port default — call out if the guide's machine has the
same conflict.

---

### Phase 1 — Core Loop (No Security Yet)

**Goal:** chat → extraction → embed → always-store as v1, end to end.
Corresponds to DESIGN.md §6.1, §6.2, and the `memories` /
`memory_versions` / `provenance` tables from §5.

- [x] Alembic migration: create `memories`, `memory_versions`,
      `provenance` tables exactly per §5 DDL (leave `dependency_edges`,
      `merkle_roots`, `trust_events`, `rollback_events` for their own
      phases so each migration maps to one demoable increment)
- [x] SQLAlchemy models for the three tables above
- [x] `services/llm_client.py`: `LLMClient` protocol,
      `TemplatedLLMClient` (canned replies), `ClaudeLLMClient`
      (Anthropic Messages API) — selected via `Settings` per open question
      #1
- [x] `services/extractor.py`: `Extractor` protocol +
      `RuleBasedExtractor` — regex/keyword matcher over a fixed predicate
      set (location, preference, skill, goal) per §6.1
- [x] `services/embedding.py`: `EmbeddingService` wrapping
      `sentence-transformers/all-MiniLM-L6-v2`, returns 384-dim vectors
- [x] `POST /chat` route: user message → `LLMClient` reply → run
      `Extractor` on the turn → for each candidate, embed it → insert
      `memories` + `memory_versions(version_number=1, decision='store',
      trust_score=100)` + `provenance` — no trust gating yet, everything
      is stored
- [x] `GET /memories`, `GET /memories/{memory_id}` — minimal read routes
      so the pipeline's output is inspectable before the dashboard exists
- [x] Frontend `Chat.tsx`: message list + input, calls `POST /chat`,
      renders reply
- [x] `lib/api.ts` typed fetch client, `lib/queries.ts` first TanStack
      Query hook (`useChat` mutation)

**Demo checkpoint:** talk to the chat UI, say "I live in Bangalore and I
like Python", confirm two rows land in `memory_versions` via
`GET /memories`. **Verified 2026-07-28** (via curl against the running
backend + Vite dev proxy, exercising the same path the browser UI takes;
`GET /memories` showed both rows -- `location: Bangalore` and
`preference: Python` -- each `trust_score=100`, `decision=store`. Also
extended beyond the checklist: `services/hashing.py` now computes
`content_hash` at write time per §6.8's formula, since that column is
`NOT NULL` and Phase 5's plan text explicitly flagged this as something
Phase 1 should not skip. **Not verified in an actual browser** (no
browser-automation tool available this session) -- component code and
`tsc -b` type-checking pass, and the identical HTTP path was exercised via
curl through the Vite proxy, but visual rendering/interaction was not
click-tested.

**Deviation from plan:** `RuleBasedExtractor`'s first regex draft was
naively greedy (`i live in ([a-zA-Z ]+)` swallowed the rest of the
sentence on inputs like "I live in Bangalore and I like Python", extracting
`location: Bangalore and I like Python`). Fixed by bounding all four
predicate regexes with a shared non-greedy + lookahead stop pattern (stops
at `and`/`but`/punctuation). Verified against the four DESIGN.md-style demo
utterances before wiring the route.

---

### Phase 2 — Retrieval + Rule-Based Trust Engine + Versioning

**Goal:** candidate memories are actually gated (store / review / reject)
and contradictory updates version instead of duplicating. Implements
§6.3, §6.4, §6.5 (rule layer only — RF comes in Phase 7), §6.6, and the
`trust_events` table.

- [x] Alembic migration: add `trust_events` table
- [x] `services/retrieval.py`: hybrid retrieval — pgvector cosine
      similarity (`ivfflat` index) + Postgres `tsvector` full-text,
      merged via reciprocal-rank fusion, top-k configurable
- [x] `services/features.py`: compute the §6.4 feature vector
      (`similarity`, `contradiction`, `source_reliability`,
      `memory_age_days`, `prior_trust_score`, `corroboration_count`,
      `conversation_recency`) for (candidate, best-match) pairs.
      Contradiction detection: rule-based negation/antonym check first,
      LLM-judge fallback via `LLMClient` for ambiguous cases
- [x] `services/trust_engine.py`: deterministic additive rule scorer
      producing the `trust_breakdown` JSON shown in §6.5's example
      (`source +30`, `semantic_similarity +24`, ...); apply decision
      thresholds (`>=70` store, `40-69` review, `<40` reject) from a
      `Settings`-configurable value, not hardcoded
- [x] `services/versioning.py`: on a contradictory update to an existing
      memory, insert `version_number + 1`, flip prior version's
      `is_active=false`, update `memories.current_version_id` and
      denormalized `memories.status`
- [x] Wire `POST /chat` pipeline: extraction → embed → retrieval →
      features → trust_engine → decision branch (store / review /
      reject) → versioning, and log one `trust_events` row per decision
- [x] `GET /trust/{version_id}` — returns score + breakdown
- [x] `GET /memories?status=` filter support (already existed from
      Phase 1; verified it composes correctly with Phase 2's new
      `status` values)

**Demo checkpoint:** say "I like Python" then later "I hate Python" in
chat — second statement should show a lower trust score, land in
review/reject depending on threshold, and NOT silently overwrite the
first memory (both versions visible via `GET /memories/{id}/history`).
**Verified 2026-07-28** via curl against the running backend (same
sequence a browser would produce): "I like Python" → v1, trust 72.0,
`store`; repeating it → v2, trust 82.0, `store` (self-corroboration, see
note below); "I hate Python" → v3, trust 34.7, `decision=reject`,
`memories.status=quarantined`, **and v1/v2 remain intact and inspectable**
via `GET /memories/{id}/history` (`is_active` correctly `false` on both,
`true` only on v3). Also ran a second scenario ("I live in Bangalore" →
"I live in Mumbai") to exercise the LLM-judge ambiguous-contradiction
fallback (same predicate, different value) — landed at trust 45.9,
`review`/`low_trust`, as expected for a genuinely ambiguous update. Backend
unit tests (`tests/unit/test_trust_engine.py`,
`test_extractor_roundtrip.py`, 10 cases) cover the rule-scorer math,
threshold branching, and the format/parse round-trip the contradiction
detector depends on — all passing. `GET /memories/{memory_id}/history`
(listed under Phase 3 below) was implemented now rather than as a
placeholder, since Phase 2's own demo checkpoint needs it to show both
versions.

**Implementation notes (design decisions not fully pinned down in
DESIGN.md, resolved here):**
- **Versioning always advances `current_version_id`, regardless of
  decision.** DESIGN.md's architecture diagram shows separate `review`
  and `reject` branches off the Trust Engine that look distinct from the
  `store` → Versioning path, which could be read as "only `store`
  actually writes a new current version." That can't be right, though:
  §6.10 step 3 of the Rollback Engine explicitly "revert[s]
  `current_version_id` to that prior version" for a poisoned descendant
  — there has to be something to revert *from*. So a `review` or
  `reject` decision still writes a new version and moves
  `current_version_id` forward; only the `trust_score`/`decision`/
  `memories.status` differ. This is what makes "second statement lands
  in review/reject and doesn't overwrite" demoable at all: the dashboard
  shows the *current* (low-trust) belief plainly, while history keeps
  the prior trusted state recoverable.
- **`memories.status` mapping:** `store`→`trusted`, `review`→`low_trust`,
  `reject`→`quarantined` (not `rejected` — matches the flow-1 pitch
  script's wording in DESIGN.md §9).
- **Rule-scorer weights** (`source` 30, `semantic_similarity` 24,
  `novelty` 24, `context` 18, `contradiction` −40, `corroboration` 10/match
  capped at 20) are original hand-tuned constants — DESIGN.md §6.5 gives
  only one illustrative example line, not a full weight table. Chosen so
  a brand-new uncontested fact stores (~72), a hard contradiction against
  a trusted memory lands in reject/quarantine territory (~35, in the
  spirit of DESIGN.md §9 flow 1's "~22–28%" though not an exact match —
  expect actual demo numbers to vary with phrasing until Phase 7's
  RF+SHAP layer replaces these constants), and a plain uncontested
  restatement of an existing fact scores *higher* than a contradicting
  one (added a small self-corroboration credit so restating something
  doesn't score worse than a brand-new claim, which the first draft of
  the formula got backwards — caught by
  `test_corroborating_update_scores_higher_than_contradicting_one`).
- **`retrieval_same_memory_threshold`** (0.5 cosine similarity, in
  `Settings`) is the cutoff for treating a retrieval hit as "this is an
  update to an existing memory" (→ versioning) vs. "this is unrelated" (→
  brand-new memory) — needed to implement §6.6 but not a named config
  value in DESIGN.md.
- **LLM-judge contradiction fallback** (§6.4): `TemplatedLLMClient`
  implements a deterministic word-overlap heuristic (no model call, no
  API key needed) so the ambiguous-case path — same predicate, different
  value, e.g. a location change — stays demoable out of the box;
  `ClaudeLLMClient` asks Claude for a real 0–1 contradiction score.

---

### Phase 3 — Admin Dashboard (Real Data, No Mocks)

**Goal:** the "guide-facing" surface starts existing. Implements the
Memories/MemoryDetail/TrustAnalysis pages from §8 against Phase 1–2 data.

- [x] `GET /memories/{memory_id}/history` — full version timeline (built
      in Phase 2's section above, since Phase 2's own checkpoint needed it)
- [x] Frontend `Dashboard.tsx` — summary tiles (counts by status), first
      real use of `dataviz`/`artifact-design` palette per open question #4
- [x] Frontend `Memories.tsx` — table: text, trust score, version count,
      status, filterable
- [x] Frontend `MemoryDetail.tsx` — trust breakdown, content hash
      (hash itself is inert until Phase 5, but the field is already on
      the row), dependency placeholder ("none yet" until Phase 4),
      version timeline
- [x] Frontend `TrustAnalysis.tsx` — the additive breakdown bars
      (+30/+24/+18/-10/+20 style) reading real `trust_breakdown` JSON
- [x] `components/StatTile/`, `components/TrustBreakdownBars/`
- [x] Admin route shell (`/admin`, `/admin/memories`,
      `/admin/memories/:id`) wired into `App.tsx`

**Demo checkpoint:** run the Phase 2 contradiction scenario in Chat, then
switch to `/admin/memories` and see both versions, trust scores, and the
breakdown bars for the rejected/low-trust one — this is the first time
the two "front doors" (§3) are demoed together. **Verified 2026-07-28**
functionally, not visually: ran the full "I like Python" / repeat / "I
hate Python" sequence through `POST /chat` via the Vite dev proxy (the
same network path the browser takes), then confirmed `GET /memories`,
`GET /memories/{id}`, and `GET /memories/{id}/history` return exactly the
data each page needs (status badge value, `trust_breakdown` for the bars,
`content_hash`, all three version rows with correct `is_active` flags).
`tsc -b && vite build` passes with zero type errors. **Not click-tested
in an actual browser** — no browser-automation tool was available this
session (same limitation noted in Phase 1's checkpoint) — so layout,
hover states, and the breakdown-bar rendering haven't been visually
confirmed, only that the components compile and the data they bind to is
correct and complete.

**Deviations from plan:**
- **`TrustAnalysis.tsx` is not a separately routed page.** Phase 3's task
  list only wires three routes (`/admin`, `/admin/memories`,
  `/admin/memories/:id`), and DESIGN.md §9's checkpoint describes seeing
  breakdown bars while already looking at a memory's versions — so the
  breakdown-bars component (`components/TrustBreakdownBars/`) is
  rendered directly inside `MemoryDetail.tsx` rather than as its own
  top-level page. `TrustAnalysis.tsx` as a standalone route can be added
  later if the dashboard grows a dedicated trust-analytics view (e.g.
  alongside Phase 8's `Analytics.tsx`).
- **`pages/AdminLayout.tsx`** (nav shell + `<Outlet/>` for the nested
  `/admin/*` routes) isn't in DESIGN.md §8's file list but is needed to
  wire the three admin routes into one shell with shared navigation —
  a structural addition, not a design change.

---

### Phase 4 — Dependency Graph

**Goal:** derivation edges are recorded and visualized. Implements §6.9
and the `dependency_edges` table.

- [x] Alembic migration: add `dependency_edges` table
- [x] `services/graph.py`: `networkx.DiGraph` built from
      `dependency_edges` rows; BFS descendants, ancestor lookup helpers
      (these are reused as-is by the Phase 6 rollback engine)
- [x] Wire edge creation into the Phase 2 pipeline: whenever retrieval
      pulls an existing memory in as supporting context for a new
      candidate, write `dependency_edges(parent=existing_version,
      child=new_version)`
- [x] `GET /memories/{memory_id}/graph` — ancestor+descendant subgraph
- [x] Frontend `Graph.tsx` + `components/GraphView/` (react-flow wrapper
      + layout algorithm, e.g. dagre)
- [x] Wire `MemoryDetail.tsx`'s dependency section to the real graph
      endpoint (replacing the Phase 3 placeholder)

**Demo checkpoint:** `scripts/seed_demo.py` pre-seeds "likes Python →
recommend Django → recommend FastAPI" (§9 flow 2 setup); Graph.tsx
renders the three-node chain. **Verified 2026-07-28**: ran
`scripts/seed_demo.py` against the docker-compose Postgres (re-run
confirmed idempotent — second run prints "already seeded" and exits
without duplicating), then hit `GET /memories/{id}/graph` for the
"preference: Python" memory via curl and got back all 3 nodes and both
`derived_from` edges. Also click-tested in an actual browser this time
(Playwright driving system Chrome against the Vite dev server, since no
project run-skill existed yet) — `/admin/memories/{id}/graph` renders the
three-node chain with dagre layout, status-colored borders, and the root
node highlighted; `MemoryDetail.tsx`'s inline dependency section renders
the same graph with a "View full graph →" link; zero browser console
errors on either page. Screenshots reviewed, not just captured.

**Implementation notes / deviations:**
- **`scripts/seed_demo.py`** wasn't itself a checklist bullet above (only
  implied by the demo checkpoint text and the §1 target repo layout), but
  was built as part of this phase since the checkpoint depends on it and
  PLAN.md §3 "Seed data" calls it the single source of truth for the flow-2
  chain. It bypasses the chat pipeline's rule-based extractor entirely
  (writes versions/edges directly through `services/versioning.py` and
  `services/graph.py`) because that extractor has no "recommend X" predicate
  category (DESIGN.md 6.1) and can't produce "recommend Django" from "likes
  Python" — there's no LLM-driven recommendation step to trigger it live.
  Idempotent via a fixed seed `conversation_id`.
- **Automatic edge wiring threshold**: added
  `Settings.dependency_edge_similarity_threshold` (default 0.3, `.env.example`
  updated) — DESIGN.md 6.9 says an edge is written "whenever retrieval pulls
  an existing memory in as supporting context," but doesn't define how
  related is "related enough." In `chat.py`, an edge is only written when a
  candidate becomes a **brand-new** memory (i.e. it wasn't treated as an
  update to an existing one) and a retrieval hit clears this similarity
  floor — an update to an existing memory isn't "derived from" itself.
- **No new `api/routes/graph.py` file.** `GET /memories/{memory_id}/graph`
  lives in `api/routes/memories.py` instead, matching how `/history` was
  already placed there in Phase 2/3 rather than its own file — DESIGN.md's
  §1 target layout doesn't actually list a `graph.py` route file, only the
  endpoint itself.
- **Frontend route**: `Graph.tsx` is mounted at
  `/admin/memories/:memoryId/graph` (not a standalone top-level route) since
  every graph view is naturally centered on one memory's ancestors/
  descendants; `MemoryDetail.tsx` links to it via "View full graph →" and
  also renders the same `GraphView` component inline at a smaller height.

---

### Phase 5 — Merkle Tree Integrity

**Goal:** tamper-evidence over the store. Implements §6.8 and the
`merkle_roots` table.

- [x] Alembic migration: add `merkle_roots` table
- [x] `services/merkle.py`: leaf hash = existing `content_hash` column;
      build tree bottom-up over active leaves ordered by `version_id`;
      root computation + persistence
- [x] Compute/store `content_hash` at write time in Phase 1/2's write
      path if not already done (`sha256(text || embedding_bytes ||
      provenance)`) — verify this was actually wired, since §5 specifies
      the column but Phase 1 tasks above didn't call it out explicitly
- [x] `POST /integrity/verify`: recompute hash per active version vs.
      stored `content_hash` (row-level tamper) + rebuild tree vs. latest
      `merkle_roots` row (structural tamper); return exact mismatched
      `version_id`(s) on failure
- [x] `GET /integrity/history` — past root snapshots
- [x] `POST /attack/tamper-db` (demo-only route): directly `UPDATE`s a
      row's `text`, bypassing the API/pipeline entirely — this must use
      raw SQL, not the ORM write path, to genuinely simulate an
      out-of-band tamper
- [x] Frontend `IntegrityCheck.tsx` — root status, "Verify Integrity"
      button, tamper result display naming the affected version

**Demo checkpoint:** §9 flow 3 — call `/attack/tamper-db`, then click
"Verify Integrity" in the dashboard, see "Database Tampered" with the
exact `version_id` named. **Verified 2026-07-28** end-to-end via curl
against the docker-compose backend: seeded the flow-2 chain, confirmed a
clean `POST /integrity/verify` (`tampered: false`, recomputed root ==
latest stored root), called `POST /attack/tamper-db` against the "likes
Python" version's raw row, confirmed `/integrity/verify` immediately
flags exactly that `version_id` (`row_mismatches`) and reports
`root_mismatch: true` with differing expected/actual root hashes — while
the two *un*touched chain members are correctly reported as untampered
(no false positives). Restored the tampered row's text via the same
endpoint and confirmed `/integrity/verify` returns clean again,
confirming the hash is sensitive to exactly the row's content and
nothing else. Also click-tested `/admin/integrity` in a real browser
(Playwright + system Chrome): stat tiles, the "Verify Integrity" button,
the green "Integrity verified" banner, and the root-history table all
render against live data with zero console errors.

**Implementation notes / deviations:**
- **Merkle root is recomputed on every write, not just on-demand.**
  `services/versioning.write_version` calls
  `merkle.compute_and_store_root` at the end of every version write
  (§6.8's "on every batch of writes" option), so `merkle_roots` is an
  exact audit trail and `/integrity/verify` always has a legitimate prior
  root to diff against, rather than requiring an explicit
  recompute-on-demand step first.
- **`/integrity/verify` is read-only.** A detected mismatch is reported,
  never "healed" by writing a new root over the evidence — matches the
  dashboard's "Verify Integrity" framing as a diagnostic, not a repair
  tool (repair is Phase 6's rollback engine's job).
- **Significant bug found and fixed while building this phase:
  pgvector's `vector` column does not round-trip float components
  bit-exactly.** `content_hash` was already computed at write time in
  Phase 1 (per that phase's own deviation note) using the in-memory
  embedding, but no code before this phase ever read `MemoryVersion.
  embedding` back out of the database — Phase 2's retrieval only ever
  used it inside a SQL `cosine_distance()` expression, never
  deserialized into Python. `verify_integrity` was the first caller to
  do that, and it immediately flagged every legitimate, untouched row as
  tampered. Root-caused empirically (see conversation/investigation, not
  just theory): Postgres's `vector` text output carries fewer significant
  digits than a full float64 repr, introducing ~1e-9 absolute noise per
  component after a write/read round-trip. A first fix (rounding the
  hashed embedding to 6 decimal places, comfortably above that noise
  floor) was **not sufficient** — with 384 independent components per
  embedding, even a >100x margin still flipped a formatted digit on 2 of
  3 rows in testing. The real fix, in `services/versioning.py`: after
  inserting a version, `db.refresh(version, attribute_names=["embedding"])`
  before computing `content_hash`, so the hash is always derived from the
  embedding *as Postgres will return it*, not the pre-write in-memory
  value — write-time and verify-time now hash identical bits by
  construction instead of racing against a precision threshold.
  `services/hashing.py` reverted to full-precision (`repr()`) formatting
  since the fix removes the need for lossy rounding. Regression tests in
  `tests/unit/test_hashing.py` document the discovered noise magnitude and
  pin the "still detects a real edit" behavior; the round-trip-specific
  behavior itself isn't unit-tested (no DB in unit tests — see below) but
  was verified live per the demo checkpoint above.
- **No DB-backed integration tests added.** `backend/tests/integration/`
  is still an empty placeholder, matching Phases 1–3's testing approach
  (curl/browser verification against a real running stack, not an
  automated Postgres test fixture). `tests/unit/test_graph.py` and
  `test_merkle.py` cover the pure-function pieces (`networkx` BFS
  helpers, `build_root`'s tree math) that don't need a database.
- **No tamper/attack buttons in `IntegrityCheck.tsx`.** Scoped exactly to
  this phase's task list ("root status, Verify Integrity button, tamper
  result display") — triggering `/attack/tamper-db` from the dashboard is
  the Attack Simulator's job (Phase 6's `Rollback.tsx`, per DESIGN.md
  §8); for now it's demo'd via direct API call, consistent with a rogue
  DBA acting out-of-band rather than through the UI.

---

### Phase 6 — Rollback Engine + Attack Simulator

**Goal:** dependency-aware recovery, the centerpiece mechanism.
Implements §6.10 and the `rollback_events` table.

- [x] Alembic migration: add `rollback_events` table
- [x] `services/rollback.py`: implement the 5-step algorithm from §6.10 —
      BFS descendants via `services/graph.py`, re-run
      features+trust_engine per descendant excluding the poisoned
      ancestor, branch on outcome (keep / revert-to-prior-version /
      reject), write one `rollback_events` row with full affected-list,
      recompute Merkle root at the end (reuses Phase 5's `merkle.py`)
- [x] `POST /rollback/{version_id}` — trigger
- [x] `GET /rollback/{rollback_id}` — status/result (for the animated
      progress UI)
- [x] `POST /attack/inject-poison` (demo-only route): force-writes a
      contradicting memory bypassing normal trust gating, for a
      reliably-reproducible demo trigger
- [x] Frontend `Rollback.tsx` — attack simulator: inject poison / tamper
      / recover buttons, animated "Finding descendants... N found...
      Restoring... Done" sequence driven by polling
      `GET /rollback/{rollback_id}`
- [x] Per-node outcome display (kept / reverted / removed) on the
      rollback result

**Demo checkpoint:** §9 flow 2 in full — mark "likes Python" poisoned,
watch the animation, confirm "recommend Django" and "recommend FastAPI"
show correct per-node outcomes and the Merkle root changed afterward.
**Verified 2026-07-28** end-to-end against the docker-compose backend: ran
`scripts/seed_demo.py`, confirmed the graph (`GET /memories/{id}/graph`)
showed the expected 3-node chain, then `POST /rollback/{version_id}` on
"preference: Python"'s current version — all three chain members came back
`outcome: removed` (each had exactly one version and no independent parent,
so none had anywhere to revert to), `memories.status` flipped to
`rolled_back` on all three, `GET /integrity/verify` confirmed the new Merkle
root matched (clean, no false tamper flags) after the rollback wrote new
versions for every affected node. Also exercised the other two outcome
branches live via a throwaway script calling `services/rollback.py`
directly (bypassing the regex extractor, same pattern as `seed_demo.py`):
(a) a poisoned memory *with* a prior version correctly came back
`reverted` to that prior version's content; (b) a descendant with two
parents, only one poisoned, correctly came back `kept` once the surviving
independent parent was found. Backend unit tests
(`tests/unit/test_rollback.py`, 10 cases) cover the pure decision logic —
`classify_outcome`'s 3-way branch and `_is_tainted`'s cascading-taint
propagation through a diamond dependency graph — independent of any DB.
Click-tested `/admin/rollback` in a real browser (Playwright + system
Chrome): all three sections render, the memory dropdowns populate from real
data, triggering a rollback shows the staged "Finding descendants..." →
per-row reveal → "Done" animation and a correct outcome table, zero console
errors. `tsc -b && vite build` passes clean. DB reset to a fresh seeded
state after each verification pass so the demo isn't left mid-rollback.

**Implementation notes / deviations:**
- **The rollback animation is a client-side staged reveal, not real
  server-side progress.** `POST /rollback/{version_id}` runs synchronously
  and returns the full result immediately (same style as
  `POST /integrity/verify`) — at demo scale (a handful of nodes) this
  resolves in well under a second, so there's no real "in-progress" state
  worth polling for. `Rollback.tsx` reveals the returned `affected` list one
  row every ~450ms via a local `setInterval`, which is what actually
  produces the "Finding descendants... N found... Restoring... Done"
  sequence DESIGN.md 6.10 describes. `GET /rollback/{rollback_id}` is real
  (reads the persisted `rollback_events` row back), for re-display after a
  page refresh — it's just not what drives the animation.
- **Outcome classification operates on the CURRENT version of each
  descendant memory, not necessarily the literal version_id a
  `dependency_edges` row points at.** An edge is only ever recorded when a
  memory is brand-new (chat.py, Phase 4), so if that memory was later
  updated again for unrelated reasons, the edge's `child_version_id` can lag
  behind `memories.current_version_id`. `services/rollback.py::_process_node`
  detects this (`memory.current_version_id != version_id` for a non-root
  node) and treats the node as already-superseded / not touched, rather than
  reverting or removing a state the graph edge doesn't actually describe
  anymore. This case doesn't arise in the seeded demo chain or `/attack/
  inject-poison` flows (every memory in those scenarios has exactly one
  version at the time it's used as a dependency parent), so it wasn't
  possible to click-test live, but the guard is there to fail safe rather
  than corrupt an unrelated later update.
- **Every outcome — kept, reverted, and removed alike — writes a *new*
  version via `services/versioning.write_version`, never mutates one in
  place.** DESIGN.md 6.10 step 3's "keep active, recompute/update trust
  score" reads like it could just update the existing row's `trust_score`,
  but that would violate the "versions are never mutated" invariant (6.6)
  everywhere else in this codebase and wouldn't produce a `content_hash`
  change for the Merkle root to react to. Writing a new version for every
  affected node is also *why* the demo checkpoint's "the Merkle root changed
  afterward" is guaranteed to be true, not just usually true.
- **`removed` sets `memories.status = "rolled_back"`, not `"quarantined"`.**
  DESIGN.md 5's status enum lists `rolled_back` separately from
  `quarantined` and this is exactly the case it's for: a memory purged as a
  *consequence of an ancestor's rollback*, not because the memory's own
  content was independently judged untrustworthy. `versioning.write_version`
  always sets status via `STATUS_BY_DECISION` (which maps `reject` ->
  `quarantined`), so `rollback.py` explicitly overrides `memory.status`
  immediately after the call for this one outcome.
- **`POST /attack/inject-poison` goes through the real write path
  (`services/versioning.write_version`), unlike `POST /attack/tamper-db`'s
  raw-SQL bypass.** The point of this route is to simulate an attacker
  whose fabricated memory *got past* the trust engine and now looks exactly
  as legitimate as anything else in the store (real `content_hash`,
  participates in the Merkle tree, can anchor dependency edges) — only
  retrieval/feature-engineering/trust-scoring are skipped, not the rest of
  the pipeline.
- **No `min_training_samples`-style gate needed here.** Phase 6 landed
  before Phase 7's RF/SHAP layer, so `rollback.py` calls
  `trust_engine.score_candidate` exactly like `chat.py` does and
  automatically inherited the RF+SHAP blend once Phase 7 was built —
  no rollback-specific changes were needed when Phase 7 landed afterward.

---

### Phase 7 — ML Trust Layer (RandomForest + SHAP)

**Goal:** the rule scorer from Phase 2 gets a real learned layer on top,
per §6.5 part 2.

- [x] `backend/app/ml/data/synthetic_examples.json` — hand-authored
      safe (paraphrase/correction) and poisoned (direct contradiction,
      low corroboration) examples over the §6.4 feature schema, per open
      question #3
- [x] `backend/app/ml/train.py` — trains
      `sklearn.ensemble.RandomForestClassifier` on synthetic data +
      anything already logged in `trust_events`; serializes to
      `app/ml/model.pkl`
- [x] `services/trust_engine.py`: load the trained RF, compute
      `100 * P(safe)`, blend with the rule score; add a
      `min_training_samples` gate below which RF output is ignored and
      the rule score is authoritative (avoids an undertrained model
      dominating early in a demo)
- [x] SHAP: `shap.TreeExplainer` on the RF, map per-feature contributions
      onto the same human-readable categories the rule scorer already
      uses, so `trust_breakdown` is populated from real SHAP values once
      the RF is live, not the hand-tuned constants
- [x] Continuous retraining hook: admin approve/reject and rollback
      events (§6.5) feed back as labels — at minimum a documented/manual
      "retrain" trigger; a live auto-retrain loop is optional polish
- [x] Update `TrustAnalysis.tsx` if the breakdown category set changes
      once SHAP output replaces hand-tuned constants

**Demo checkpoint:** re-run §9 flow 1 (poison + reject live) and confirm
the breakdown panel is now backed by real SHAP values, not the
Phase 2 constants — the "why 82%" explanation should still read
identically to the user even though the mechanism underneath changed.
**Verified 2026-07-28**: ran `python -m app.ml.train` (60 synthetic
examples, 0 real logged yet since the DB was freshly reset — trains and
saves `app/ml/model.pkl` without needing a live Postgres at all), restarted
the backend to pick up the new model, then re-ran the exact flow-1 sequence
live via `POST /chat`: "I like Python" against the seeded "preference:
Python" memory landed as a corroborating v2 at trust 78.75 (`store`) with a
`trust_breakdown` keyed by real feature names (`baseline`,
`contradiction`, `similarity`, ...) instead of the Phase 2 constants;
"I hate Python" landed as v3 at trust 25.9 (`decision=reject`,
`memories.status=quarantined`), `contradiction` contributing -28.6 toward
P(safe) — same overall shape and outcome as Phase 2's original 34.7,
different mechanism underneath, exactly per the checkpoint. `GET /memories/
{id}/history` shows the mechanism transition directly: v1 (seeded before
`model.pkl` existed) still carries the old rule-engine breakdown keys,
v2/v3 (created after training) carry the new SHAP keys — both are correct
for when they were written, which is itself a nice demonstration of the
cold-start → trained handoff. Click-tested `/admin/memories/{id}` in a real
browser (Playwright + system Chrome): the SHAP breakdown renders through
the *same* `TrustBreakdownBars` component with updated human-readable
labels, zero console errors. Backend unit tests
(`tests/unit/test_trust_engine_ml.py`, 7 cases) train a real (tiny)
RandomForestClassifier in-process — not a mock — to exercise the actual
`shap.TreeExplainer` code path, and cover: below-`min_training_samples`
falls back to the rule score exactly; a missing `model.pkl` does the same;
`rf_blend_weight=1.0`/`0.0` reduce to pure rule/pure RF respectively; the
breakdown key set is exactly `FEATURE_NAMES ∪ {"baseline"}`; and the
`_load_bundle`/`clear_model_cache` file-loading path itself, via a real
pickled bundle written to a tmp path. All 43 backend unit tests pass
(`pytest -q`); `tsc -b && vite build` passes clean. DB reset to the pristine
seeded state after verification.

**Implementation notes / deviations:**
- **The trust_breakdown *key set* changes once the RF is live** — from the
  Phase 2 rule scorer's 6 named categories (`source`,
  `semantic_similarity`, ...) to the raw §6.4 feature names (`similarity`,
  `contradiction`, `source_reliability`, `memory_age_days`,
  `prior_trust_score`, `corroboration_count`, `conversation_recency`,
  `has_match`) plus a `baseline` entry, each a real SHAP contribution
  (scaled ×100 into the same "points" register the rule scorer used) toward
  the RF's own `P(safe)`. PLAN.md's own Phase 7 task list anticipated this
  exact possibility ("Update `TrustAnalysis.tsx` if the breakdown category
  set changes"), and `shap.TreeExplainer` guarantees
  `sum(shap_values) + expected_value == predict_proba` (verified
  empirically against the installed shap 0.52.0's actual output shape,
  `(n_samples, n_features, n_classes)`, before wiring this in) — so this
  breakdown is an exact decomposition of the model's own probability, not
  an approximation dressed up to look like one. `components/
  TrustBreakdownBars` needed no structural changes (it already falls back
  to the raw key name for anything not in its label map); only its `LABELS`
  map was extended with human-readable names for the new keys, so both the
  Phase 2 and Phase 7 breakdown shapes render identically well through the
  same component.
- **`min_training_samples` gates on a sample count baked into `model.pkl`
  at train time, not a live DB query at score time.** `services/
  trust_engine.py::score_candidate` is deliberately DB-free (a documented
  design constraint from Phase 2, kept intact here) so it stays trivially
  unit-testable; `app/ml/train.py` records how many examples it trained on
  (`n_samples`) directly in the pickled bundle, and `score_candidate` reads
  that number back rather than counting `trust_events` rows itself on every
  scoring call.
- **The 60-example synthetic dataset clears `min_training_samples=50` on
  its own, with zero real logged examples needed.** This was a deliberate
  choice, not an accident: PLAN.md's own "every phase must leave the demo
  runnable" ground rule means the guide shouldn't have to script 50 chat
  turns before the ML layer visibly kicks in — running `python -m app.ml.
  train` once, immediately after `git clone`, is enough. Real logged
  `trust_events`/`rollback_events` outcomes (see below) still blend in
  additively on top once they exist.
- **Real-outcome retraining reuses `rollback_events`, since no admin
  approve/reject UI exists yet.** DESIGN.md 6.5 names two feedback signals:
  "admin approve/reject" and "rollback triggered = retroactive 'poisoned'
  label." Only the second exists as a real feature (Phase 6). `app/ml/
  train.py::_load_real_examples` joins `rollback_events.affected_version_ids`
  back to each affected version's *original* `trust_events` row (the one
  from when it was first created/updated) and derives a label from the
  rollback's verdict: `kept` → safe (1), `reverted`/`removed` → poisoned
  (0). This is why `chat.py`'s `TrustEvent.details` was extended to store
  `{"breakdown":..., "features": vars(feature_vector)}` instead of just the
  breakdown — the raw §6.4 feature vector is what training actually needs,
  and the breakdown alone (Phase 2's original behavior) doesn't reconstruct
  it. `services/rollback.py` was already logging both keys from the start
  (Phase 6 predates this note but was written with this in mind).
- **Training is best-effort against the DB, never a hard requirement.**
  `app/ml/train.py::_load_real_examples` catches any DB connection or query
  failure and falls back to synthetic-only data with a printed warning,
  rather than raising — so `python -m app.ml.train` works standalone
  (verified above) even before `docker-compose up -d` has ever been run.
- **No automatic retrain loop or `/ml/retrain` HTTP endpoint.** PLAN.md
  explicitly calls a live auto-retrain loop "optional polish" and asks only
  for "at minimum a documented/manual retrain trigger" — `python -m app.ml.
  train`, documented above and in this file, satisfies that bar without the
  added surface area (and cache-invalidation-on-restart question) a
  dashboard-triggered retrain endpoint would introduce for no immediate
  demo benefit.
- **`RandomForestClassifier(n_estimators=200, max_depth=6, random_state=42,
  class_weight="balanced")`** — `max_depth=6` caps overfitting on a
  ~60-example dataset (unbounded depth would let individual trees memorize
  single points); `n_estimators=200` keeps SHAP's per-tree-averaged
  contributions stable run-to-run; `random_state=42` matches this project's
  existing convention of pinning anything that should reproduce identically
  across a demo rehearsal (`scripts/seed_demo.py`'s fixed conversation_id,
  the RRF constant, etc.) — these aren't tuned against a held-out set (there
  isn't one at this scale), just reasonable, documented defaults.
- **Bug found and fixed while building this phase: training `model.pkl`
  locally broke Phase 2's own unit tests.** `tests/unit/test_trust_engine.py`
  asserts on rule-scorer-specific breakdown keys (`novelty`, `corroboration`,
  ...) via `score_candidate`. Once this phase made `score_candidate` a
  blending entry point that transparently picks up `app/ml/model.pkl` if
  it exists on disk, those exact same tests started failing the moment
  `python -m app.ml.train` had been run at least once locally — not because
  the rule engine changed, but because the test suite's pass/fail status
  had accidentally started depending on incidental file-system state (did
  *this* machine happen to have a trained model sitting around) rather than
  the code under test. Fixed by pointing that file's tests at the newly-
  extracted `_score_rule` (the pure rule-math function `score_candidate` now
  wraps) instead of `score_candidate` itself — they were always testing the
  deterministic rule scorer specifically, so that's the correct unit for
  them to call regardless of what Phase 7 does around it. This is exactly
  the kind of drift `tests/unit/test_trust_engine_ml.py`'s tests avoid by
  monkeypatching `_load_bundle` explicitly in every case rather than relying
  on (or being tripped up by) whatever `model.pkl` happens to exist.

---

### Phase 8 — Analytics, Logs, Demo Rehearsal

**Goal:** polish pass + full run-through of the pitch script (§9).

- [x] `GET /analytics/summary` — counts by status, rollback counts
- [x] `GET /logs` — `trust_events` feed, paginated
- [x] Frontend `Analytics.tsx` — trend charts (trusted vs. rejected over
      time, rollback events) via `recharts`, following the `dataviz`
      skill's palette/interaction rules
- [x] Frontend `Logs.tsx` — raw `trust_events` feed table
- [x] `GET /search?q=...` (if not already added in Phase 2/4) — exposes
      the same hybrid retrieval used internally, per §9 flow 5
- [x] Timeline/UI polish pass across all admin pages
- [x] Full rehearsal of all 5 flows in §9 back-to-back, in order, timed
- [x] Fix whatever breaks during rehearsal (this is expected — treat it
      as the actual acceptance test for the MVP, not a formality)

**Demo checkpoint:** all 5 §9 flows run back-to-back without restarting
the app or reseeding mid-script. **Verified 2026-07-29** via curl against
the docker-compose backend, run in this order on one freshly-seeded chain
(not the §9 listing order, since flow 2 needs the seed chain intact before
flow 1 touches the same "likes Python" memory): flow 5 (search) → flow 2
(rollback) → flow 1 (poison+reject) → flow 4 (explainability) → flow 3
(tamper). All 5 passed: search ranked `goal: learn Django` top for
"backend frameworks" (0.33 similarity); rollback returned `removed` for
all 3 chain members with a clean `/integrity/verify` immediately after;
"I like Python" → "I hate Python" landed at **trust 25.9%, decision=reject,
status=quarantined** — inside DESIGN.md §9 flow 1's "~22–28%" callout;
the SHAP breakdown (`contradiction: -28.6`, `baseline: 50.1`, ...) rendered
identically through the existing `TrustBreakdownBars` component; tamper-db
against the active version was caught exactly (`row_mismatches` named that
one `version_id`, `root_mismatch: true`), and restoring it returned
`/integrity/verify` to clean. `GET /analytics/summary` and `GET /logs`
reflected all of the above correctly once each flow ran (trend chart
showed 4 stored / 4 rejected / 1 rollback on the one active day; logs feed
showed all 5 `trust_events` rows newest-first with correct decision
badges). Backend: `pytest -q` — 53 tests pass (48 pre-existing + 5 new
`test_analytics.py` cases). Frontend: `tsc -b && vite build` clean.
Click-tested `/admin/analytics`, `/admin/logs`, `/admin/memories`,
`/admin/rollback` in a real browser (Playwright + system Chrome, both
light and dark) with zero console errors; screenshots reviewed, not just
captured. DB reset to a fresh `seed_demo.py` state after verification, per
this file's own "Seed data" convention.

**Implementation notes / deviations:**
- **Two real, demo-breaking bugs were found and fixed while rehearsing —
  this is exactly what this phase's "fix whatever breaks... the actual
  acceptance test" instruction is for, not a formality:**
  1. **The `ivfflat` vector index silently dropped rows at this project's
     scale.** `GET /search?q=backend frameworks` returned an empty list
     against the 3-memory seed chain even though `goal: learn Django` is
     obviously relevant — traced (via `EXPLAIN`, and by toggling
     `enable_indexscan` locally) to Postgres switching from a sequential
     scan to `Index Scan using ix_memory_versions_embedding` the moment an
     `ORDER BY embedding <=> :query LIMIT :k` shape appears, and pgvector's
     ivfflat defaults to 100 list-clusters probing only 1 per query — over
     a handful of demo-scale rows nearly every cluster is empty, so a
     query vector can easily land in an empty one and return nothing, even
     when it's identical to a stored embedding. Fixed by dropping the
     index entirely (migration `4f1a9b3c7d2e`): DESIGN.md's own non-goals
     ("production-scale vector search... pgvector is enough") already
     scope this project below the size where an approximate index earns
     its keep, and an exact sequential scan has no `lists`/`probes` knob
     to mistune as the row count changes. This also means Phase 2/4's
     retrieval was silently degraded the same way the whole time
     (`hybrid_search`'s vector leg, not just the new `/search` route) —
     it just hadn't been caught because chat-driven demo phrasings
     happened to land in a populated cluster often enough not to notice.
  2. **`merkle_roots.computed_at` used transaction time, not statement
     time**, so every root written within one multi-write transaction
     (e.g. `POST /rollback/{version_id}` recovering a 3-node chain calls
     `compute_and_store_root` three times) got an *identical* timestamp,
     and `latest_root()`'s tiebreak on `root_id` (a random UUID,
     uncorrelated with insertion order) could then pick a stale
     mid-transaction root instead of the true final one. Caught live: a
     clean rollback was immediately followed by `POST /integrity/verify`
     reporting `tampered: true` / `root_mismatch: true` with
     `row_mismatches` empty — i.e. nothing was actually tampered, the
     "expected" root was just wrong. Confirmed by manually rebuilding the
     tree from ground-truth `content_hash` values and matching
     `verify_integrity`'s independently-recomputed `actual_root` exactly.
     Fixed with a real monotonic counter (migration `8b2e5f6a1c9d`: a
     `sequence_number` column backed by a Postgres sequence, `nextval()`
     called once per row regardless of transaction boundaries) and
     repointing `merkle.latest_root()` and `GET /integrity/history`'s
     ordering at it instead of `computed_at`/`root_id`. This is a
     correctness bug in Phase 5/6's own mechanism, not new Phase 8 surface
     — flagged here because Phase 8's full-rehearsal pass is what
     surfaced it (a single-write action never hits the tie).
  Both fixes required a full DB reset (`TRUNCATE` + re-`seed_demo.py`,
  confirmed with the user first since it's destructive) to clear
  historical rows written before the fixes existed, whose relative order
  couldn't be reconstructed after the fact — the running system's
  behavior going forward is what's fixed, not the stale rows themselves.
- **`GET /analytics/summary`'s trend field buckets by calendar date**, not
  a rolling window — `services/analytics.py::build_trend` is a pure
  function (raw `(created_at, decision)` tuples and rollback timestamps
  in, one row per day out) specifically so the bucketing logic is
  unit-testable without a database, matching this codebase's existing
  `trust_engine`/`graph`/`rollback`-style split between pure decision
  logic and DB IO. `tests/unit/test_analytics.py` (5 cases) covers
  cross-date bucketing, rollback-only dates, unknown decision values, and
  sort order.
- **Analytics.tsx's 4-series trend chart reuses the fixed status-role hex
  values** (`#0ca30c`/`#fab219`/`#d03b3b`/`#ec835a`), not fresh categorical
  colors — store/review/reject/rollback genuinely correspond to the
  trusted/low_trust/quarantined/rolled_back state vocabulary the rest of
  the dashboard already uses (`lib/status.ts`, `GraphView`), so this is
  the dataviz skill's "status color, not identity color" case, not a
  4-series categorical chart. Chart chrome (gridlines, axis, tooltip) is
  computed via a `prefers-color-scheme` media-query hook rather than
  Tailwind `dark:` classes, since those are real SVG props recharts
  renders directly — matching the precedent already set by `GraphView`'s
  status-color comment for the same reason. Legend, tooltip (line-key
  style, value-leads-label per the skill's interaction rules), rounded
  bar ends, and a plain-HTML "table view" twin under the chart were all
  built by hand rather than via `recharts`' defaults, to satisfy the
  dataviz skill's mark/legend/table-view requirements exactly.
- **`recharts` pinned to v3, not the v2 in PLAN.md's original tech
  stack line** — v2 is EOL upstream (deprecation warning on install
  pointing at the v3 migration guide) and needed an explicit `react-is`
  dependency added by hand (`recharts` lists it as a peer dependency that
  npm didn't auto-install); v3 installed clean against React 19 with no
  peer-dependency conflicts.
- **No standalone `Search.tsx` page.** DESIGN.md §8's page list doesn't
  include one — flow 5 is written as a direct-API demo (`GET
  /search?q=...`) like Phase 5's `/attack/tamper-db` was before Phase 6
  gave attacks a UI. A compact "Semantic search" widget was still added
  inline to `Memories.tsx` (not a new route) so flow 5 is also
  browser-demoable, not curl-only — a small, tightly-scoped addition in
  the spirit of "every phase leaves the demo runnable," not a new page.
- **`Logs.tsx`'s status pill is colored by `decision` (store/review/
  reject), not `event_type`.** The first draft colored the "Event" column
  (created/updated/rolled_back/admin_override) using a fixed event→status
  map, which looked wrong immediately on inspection: a `rolled_back`
  event's own `decision` can itself be store/review/reject (a `kept` or
  `reverted` rollback outcome re-scores through the normal trust engine;
  only `removed` hardcodes `reject`), so a coarse event-type→color mapping
  produced a green "updated" pill sitting next to a red "reject" decision
  in the same row during rehearsal. Fixed by coloring the existing
  `Decision` column with the same `lib/status.ts` palette instead, and
  leaving `Event` as plain text — the decision is the actual trust-engine
  outcome the color should carry, the event type is just context for it.
- **No `min_training_samples`-style config added for analytics.** Nothing
  in this phase needed a new `Settings` value — `/analytics/summary` and
  `/logs` are read-only aggregations over existing tables with no
  threshold to tune.

---

## 3. Cross-Cutting Concerns

- **Testing.** Unit tests matter most for the logic that's easy to get
  subtly wrong and hard to eyeball in a demo: `trust_engine.py` (rule
  scorer math + threshold branching), `merkle.py` (hash/root
  recomputation and tamper detection), `rollback.py` (descendant
  transitive closure, outcome branching). Cover these in
  `backend/tests/unit/` as they're built, not retroactively. Integration
  tests for the `POST /chat` → store pipeline and `POST /rollback`
  end-to-end belong in `backend/tests/integration/`. Frontend tests are
  optional for MVP — the demo rehearsal in Phase 8 is the real
  acceptance check.
- **Seed data.** `scripts/seed_demo.py` should be idempotent (safe to
  re-run against a fresh `docker-compose` volume) and is the single
  source of truth for the §9 flow 2 chain — don't hand-create that data
  via the UI during rehearsals.
- **Config.** All thresholds (`trust` decision cutoffs, retrieval
  top-k, `min_training_samples`) live in `Settings`, not hardcoded in
  services — the demo script depends on being able to tune these live if
  a threshold doesn't produce the expected score on stage.
- **No mocks in the dashboard.** Per Phase 3's explicit instruction in
  §11, every admin page reads real backend data from the first commit
  that adds it — no placeholder/mock JSON that gets swapped later.

## 4. Definition of Done (MVP)

- [x] All 8 phases' demo checkpoints pass in one continuous session.
- [x] All 5 §9 attack/demo flows run without manual DB intervention.
- [x] `docker-compose up -d && uvicorn ... && npm run dev` is the entire
  setup story — no undocumented manual steps.
- [x] Open questions in §0 are either confirmed or explicitly still using
  their proposed default, and that's noted in this file's changelog
  (add a dated line under a "Decisions" heading here once each is
  resolved, rather than editing DESIGN.md's §12 in place).

**MVP complete as of 2026-07-29** (Phase 8's rehearsal). All 4 open
questions in §0 resolved (question #3 dated below; #1, #2, #4 confirmed
as their proposed defaults, never revisited — `TemplatedLLMClient` default,
local-laptop-only, dataviz default palette).

### Decisions

- **2026-07-28 — Open question #3 (RF bootstrap dataset):** confirmed as
  proposed. `backend/app/ml/data/synthetic_examples.json` is hand-authored
  and checked into the repo (60 examples, generated once via a throwaway
  script for consistency and re-run with `python -m app.ml.train` — not
  regenerated fresh on every run), matching the "reproducible demo,
  diffable, reviewable" reasoning §0 gave for this default. See Phase 7's
  implementation notes for how it's combined with real logged outcomes.
- **2026-07-29 — Two correctness bugs in Phase 5/6's own mechanisms,
  found via Phase 8's full-rehearsal pass, not new Phase 8 surface:**
  the `ivfflat` vector index silently dropping rows at demo scale
  (migration `4f1a9b3c7d2e`, drops it — exact sequential scan instead),
  and `merkle_roots`' latest-root lookup picking a stale root after a
  multi-write transaction like a rollback (migration `8b2e5f6a1c9d`, adds
  a real monotonic `sequence_number`). Full detail in Phase 8's
  implementation notes above. Neither is a design change — both are the
  kind of thing this file's own ground rule ("fix whatever breaks during
  rehearsal... the actual acceptance test") anticipated.

---
*This plan tracks DESIGN.md v1 (2026-07-28). If DESIGN.md's architecture
changes materially, update this file's affected phase(s) in the same
change rather than letting them drift out of sync.*
