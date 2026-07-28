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

- [ ] Alembic migration: add `dependency_edges` table
- [ ] `services/graph.py`: `networkx.DiGraph` built from
      `dependency_edges` rows; BFS descendants, ancestor lookup helpers
      (these are reused as-is by the Phase 6 rollback engine)
- [ ] Wire edge creation into the Phase 2 pipeline: whenever retrieval
      pulls an existing memory in as supporting context for a new
      candidate, write `dependency_edges(parent=existing_version,
      child=new_version)`
- [ ] `GET /memories/{memory_id}/graph` — ancestor+descendant subgraph
- [ ] Frontend `Graph.tsx` + `components/GraphView/` (react-flow wrapper
      + layout algorithm, e.g. dagre)
- [ ] Wire `MemoryDetail.tsx`'s dependency section to the real graph
      endpoint (replacing the Phase 3 placeholder)

**Demo checkpoint:** `scripts/seed_demo.py` pre-seeds "likes Python →
recommend Django → recommend FastAPI" (§9 flow 2 setup); Graph.tsx
renders the three-node chain.

---

### Phase 5 — Merkle Tree Integrity

**Goal:** tamper-evidence over the store. Implements §6.8 and the
`merkle_roots` table.

- [ ] Alembic migration: add `merkle_roots` table
- [ ] `services/merkle.py`: leaf hash = existing `content_hash` column;
      build tree bottom-up over active leaves ordered by `version_id`;
      root computation + persistence
- [ ] Compute/store `content_hash` at write time in Phase 1/2's write
      path if not already done (`sha256(text || embedding_bytes ||
      provenance)`) — verify this was actually wired, since §5 specifies
      the column but Phase 1 tasks above didn't call it out explicitly
- [ ] `POST /integrity/verify`: recompute hash per active version vs.
      stored `content_hash` (row-level tamper) + rebuild tree vs. latest
      `merkle_roots` row (structural tamper); return exact mismatched
      `version_id`(s) on failure
- [ ] `GET /integrity/history` — past root snapshots
- [ ] `POST /attack/tamper-db` (demo-only route): directly `UPDATE`s a
      row's `text`, bypassing the API/pipeline entirely — this must use
      raw SQL, not the ORM write path, to genuinely simulate an
      out-of-band tamper
- [ ] Frontend `IntegrityCheck.tsx` — root status, "Verify Integrity"
      button, tamper result display naming the affected version

**Demo checkpoint:** §9 flow 3 — call `/attack/tamper-db`, then click
"Verify Integrity" in the dashboard, see "Database Tampered" with the
exact `version_id` named.

---

### Phase 6 — Rollback Engine + Attack Simulator

**Goal:** dependency-aware recovery, the centerpiece mechanism.
Implements §6.10 and the `rollback_events` table.

- [ ] Alembic migration: add `rollback_events` table
- [ ] `services/rollback.py`: implement the 5-step algorithm from §6.10 —
      BFS descendants via `services/graph.py`, re-run
      features+trust_engine per descendant excluding the poisoned
      ancestor, branch on outcome (keep / revert-to-prior-version /
      reject), write one `rollback_events` row with full affected-list,
      recompute Merkle root at the end (reuses Phase 5's `merkle.py`)
- [ ] `POST /rollback/{version_id}` — trigger
- [ ] `GET /rollback/{rollback_id}` — status/result (for the animated
      progress UI)
- [ ] `POST /attack/inject-poison` (demo-only route): force-writes a
      contradicting memory bypassing normal trust gating, for a
      reliably-reproducible demo trigger
- [ ] Frontend `Rollback.tsx` — attack simulator: inject poison / tamper
      / recover buttons, animated "Finding descendants... N found...
      Restoring... Done" sequence driven by polling
      `GET /rollback/{rollback_id}`
- [ ] Per-node outcome display (kept / reverted / removed) on the
      rollback result

**Demo checkpoint:** §9 flow 2 in full — mark "likes Python" poisoned,
watch the animation, confirm "recommend Django" and "recommend FastAPI"
show correct per-node outcomes and the Merkle root changed afterward.

---

### Phase 7 — ML Trust Layer (RandomForest + SHAP)

**Goal:** the rule scorer from Phase 2 gets a real learned layer on top,
per §6.5 part 2.

- [ ] `backend/app/ml/data/synthetic_examples.json` — hand-authored
      safe (paraphrase/correction) and poisoned (direct contradiction,
      low corroboration) examples over the §6.4 feature schema, per open
      question #3
- [ ] `backend/app/ml/train.py` — trains
      `sklearn.ensemble.RandomForestClassifier` on synthetic data +
      anything already logged in `trust_events`; serializes to
      `app/ml/model.pkl`
- [ ] `services/trust_engine.py`: load the trained RF, compute
      `100 * P(safe)`, blend with the rule score; add a
      `min_training_samples` gate below which RF output is ignored and
      the rule score is authoritative (avoids an undertrained model
      dominating early in a demo)
- [ ] SHAP: `shap.TreeExplainer` on the RF, map per-feature contributions
      onto the same human-readable categories the rule scorer already
      uses, so `trust_breakdown` is populated from real SHAP values once
      the RF is live, not the hand-tuned constants
- [ ] Continuous retraining hook: admin approve/reject and rollback
      events (§6.5) feed back as labels — at minimum a documented/manual
      "retrain" trigger; a live auto-retrain loop is optional polish
- [ ] Update `TrustAnalysis.tsx` if the breakdown category set changes
      once SHAP output replaces hand-tuned constants

**Demo checkpoint:** re-run §9 flow 1 (poison + reject live) and confirm
the breakdown panel is now backed by real SHAP values, not the
Phase 2 constants — the "why 82%" explanation should still read
identically to the user even though the mechanism underneath changed.

---

### Phase 8 — Analytics, Logs, Demo Rehearsal

**Goal:** polish pass + full run-through of the pitch script (§9).

- [ ] `GET /analytics/summary` — counts by status, rollback counts
- [ ] `GET /logs` — `trust_events` feed, paginated
- [ ] Frontend `Analytics.tsx` — trend charts (trusted vs. rejected over
      time, rollback events) via `recharts`, following the `dataviz`
      skill's palette/interaction rules
- [ ] Frontend `Logs.tsx` — raw `trust_events` feed table
- [ ] `GET /search?q=...` (if not already added in Phase 2/4) — exposes
      the same hybrid retrieval used internally, per §9 flow 5
- [ ] Timeline/UI polish pass across all admin pages
- [ ] Full rehearsal of all 5 flows in §9 back-to-back, in order, timed
- [ ] Fix whatever breaks during rehearsal (this is expected — treat it
      as the actual acceptance test for the MVP, not a formality)

**Demo checkpoint:** all 5 §9 flows run back-to-back without restarting
the app or reseeding mid-script.

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

- All 8 phases' demo checkpoints pass in one continuous session.
- All 5 §9 attack/demo flows run without manual DB intervention.
- `docker-compose up -d && uvicorn ... && npm run dev` is the entire
  setup story — no undocumented manual steps.
- Open questions in §0 are either confirmed or explicitly still using
  their proposed default, and that's noted in this file's changelog
  (add a dated line under a "Decisions" heading here once each is
  resolved, rather than editing DESIGN.md's §12 in place).

---
*This plan tracks DESIGN.md v1 (2026-07-28). If DESIGN.md's architecture
changes materially, update this file's affected phase(s) in the same
change rather than letting them drift out of sync.*
