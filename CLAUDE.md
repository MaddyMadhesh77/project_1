# RecoverMem

Security middleware between an LLM agent and its long-term memory store —
trust-scores candidate memories before persisting, versions instead of
overwriting, tamper-evidences the store with a Merkle tree, and tracks
derivation dependencies so a poisoned memory and everything derived from it
can be found and rolled back.

Full architecture, data model, API surface, and build roadmap: see
[docs/DESIGN.md](docs/DESIGN.md) — read it before proposing design changes,
rather than re-deriving the architecture from scratch.

This is a demo/pitch project built to show a "guide" (mentor/evaluator).
Prioritize keeping the project demoable at every phase over finishing
components in isolation (see DESIGN.md §11 for phases).

## Status
All 8 phases complete (MVP) — see [docs/PLAN.md](docs/PLAN.md) for the
checklist, per-phase demo checkpoints, and the implementation
notes/deviations recorded under each phase.

Trust gating is real as of Phase 2: every extracted candidate is scored
by a deterministic additive rule engine (`services/trust_engine.py`)
against hybrid retrieval + feature engineering, and lands as
store/review/reject (`memories.status` = trusted/low_trust/quarantined).
Contradictory updates version instead of overwriting — `current_version_id`
always advances to the newest version regardless of decision (so a
rejected update still becomes "current," flagged via status, with prior
versions intact in history — see PLAN.md Phase 2's implementation notes
for why). The admin dashboard (`/admin`, `/admin/memories`,
`/admin/memories/:id`, `/admin/memories/:id/graph`, `/admin/integrity`,
`/admin/rollback`) reads this real data — no mocks.

Dependency graph is real as of Phase 4: `dependency_edges` rows are
written whenever a brand-new memory's retrieval hit clears
`Settings.dependency_edge_similarity_threshold`, loaded into a
`networkx.DiGraph` (`services/graph.py`), and exposed via
`GET /v1/memories/{id}/graph` + `GraphView`'s `@xyflow/react` view (laid
out with `elkjs`).
`scripts/seed_demo.py` idempotently seeds the §9 flow-2 demo chain
("likes Python" → "recommend Django" → "recommend FastAPI") directly
through the versioning/graph services, since the rule-based extractor has
no way to produce a "recommend X" memory on its own.

Merkle tamper-evidence is real as of Phase 5: `content_hash` (sha256 of
text + embedding + provenance, computed in `services/hashing.py`) is
set on every version, and a new root is appended to `merkle_roots` once per
writing request (`services/merkle.compute_and_store_root`, called by the
chat/attack/rollback/seed paths after their writes — not inside
`write_version`, so a multi-write request pays for one tree rebuild).
`GET /v1/integrity/verify` recomputes per-row hashes (every version,
superseded ones included) and the tree root (active versions) against
current DB content and reports exact mismatched `version_id`s;
`POST /v1/attack/tamper-db` simulates an out-of-band tamper via raw SQL for
the demo. Note for anyone touching `services/hashing.py` or
`services/versioning.py`: pgvector's `vector` column does **not**
round-trip float components bit-exactly (~1e-9 noise per component after
a write/read cycle) — `content_hash` must be computed from the embedding
*after* `db.refresh()`, not the pre-write in-memory value, or
`verify_integrity` will false-positive on untouched rows. See PLAN.md's
Phase 5 implementation notes for how this was found and fixed.

Dependency-aware rollback is real as of Phase 6: `POST /rollback/{version_id}`
(`services/rollback.py`) BFS's a poisoned version's descendants via
`services/graph.py`, re-evaluates each one with the poisoned ancestor's
support excluded, and per node either keeps it (an independent parent still
corroborates it), reverts it (no independent support, but the memory has a
prior version to fall back to), or removes it (`memories.status` =
`rolled_back`, neither) — never mutating a row, always writing a new
version like everywhere else in this codebase. Support is judged per parent
*memory* using the earliest version the node has an edge from
(`rollback.valid_sources`): `carry_forward_edges` copies edges onto every
newer version, and those copies must not count as independent support.
Reverts only go back to a version that isn't itself derived from the poison.
A version that's no longer current — including the poisoned version itself,
when it was already replaced — is recorded as `superseded` and left alone,
so newer state is never clobbered, while its descendants are still
recovered. `POST /attack/inject-poison`
force-writes a memory through the real versioning/hashing/Merkle pipeline
while bypassing only the trust engine, for a reliably-reproducible
"attacker got past the gate" demo trigger; `/attack/tamper-db` (Phase 5)
remains the separate raw-SQL out-of-band tamper simulation. `Rollback.tsx`
(`/admin/rollback`) is the attack-simulator UI: inject poison / tamper DB /
mark-poisoned-and-recover, with a staged client-side reveal of the
per-node outcome (the rollback itself runs synchronously, like
`/integrity/verify` — there's no real long-running job to poll at demo
scale). See PLAN.md's Phase 6 implementation notes for the taint-propagation
and "operates on the current version, not a stale graph-edge snapshot"
details.

The RandomForest+SHAP trust layer is real as of Phase 7:
`services/trust_engine.py` loads `app/ml/model.pkl` (trained via
`python -m app.ml.train` on `app/ml/data/synthetic_examples.json` plus any
real rollback-labelled outcomes it can reach) and blends `100 * P(safe)`
with the Phase 2 rule score once the model's recorded `n_real_samples`
clears `Settings.min_training_samples` (default 50) — mode `rf_real`. The
60-example synthetic set does **not** count toward that gate on its own;
with `ML_BOOTSTRAP_ON_SYNTHETIC=true` (set in `.env.example` for the demo,
off by default in `Settings`) the synthetic+real *total* is allowed to clear
it instead — mode `rf_bootstrap`, which `GET /v1/trust/model` reports and
the UI labels "bootstrap model". Otherwise, or if `model.pkl` doesn't exist
yet, scoring is 100% the rule engine, so the demo never depends on training
having happened. Once live, `trust_breakdown` is populated from real
`shap.TreeExplainer` per-feature contributions (keyed by the raw §6.4
feature names + `baseline`, not the Phase 2 rule categories). Those bars sum
to the model's own score, not the stored blended score —
`TrustBreakdownBars` shows both. Retraining is a manual step
(`python -m app.ml.train`, which also prints the resulting scorer mode);
there's no auto-retrain loop by design (see PLAN.md Phase 7 notes).

Analytics/Logs/Search are real as of Phase 8: `GET /analytics/summary`
(`services/analytics.py`) returns status/decision counts and a per-day
trend of store/review/reject/rollback events, feeding `Analytics.tsx`'s
`recharts` trend chart; `GET /logs` is a paginated `trust_events` feed
(`Logs.tsx`); `GET /search?q=...` exposes the same `services/retrieval.py`
hybrid search the chat pipeline already used internally, demoable both via
curl (§9 flow 5) and a "Semantic search" widget on `Memories.tsx`. Phase 8's
full back-to-back rehearsal of all 5 §9 flows is what a single-phase
verification pass wouldn't have caught two real bugs in earlier phases'
own mechanisms:

- **pgvector's `ivfflat` index silently drops rows at this project's
  scale.** It defaults to 100 list-clusters probing only 1 per query;
  over a handful of demo-scale rows, `ORDER BY embedding <=> :query LIMIT
  :k` (the shape that makes Postgres prefer the index over a sequential
  scan) can miss obviously-relevant, even identical, rows. Fixed by
  dropping the index (migration `4f1a9b3c7d2e`) — DESIGN.md's own
  non-goals already scope this project below the size where an
  approximate index earns its keep, and an exact sequential scan has no
  `lists`/`probes` knob to mistune as row count grows. This silently
  affected `services/retrieval.py::hybrid_search`'s vector leg since
  Phase 2, not just the new `/search` route — chat-driven demo phrasings
  had just been landing in a populated cluster often enough not to notice.
- **`merkle_roots.computed_at` used transaction time, not statement
  time**, so multiple roots written within one multi-write transaction
  (e.g. a rollback recovering a 3-node chain calls
  `compute_and_store_root` three times) shared one timestamp, and
  `latest_root()`'s `root_id`-tiebreak (a random UUID) could pick a stale
  mid-transaction root — caught as `/integrity/verify` falsely
  reporting `tampered: true` immediately after a clean rollback. Fixed
  with a real monotonic `sequence_number` column (migration
  `8b2e5f6a1c9d`) backing `merkle.latest_root()` and
  `GET /integrity/history`'s ordering instead of `computed_at`/`root_id`.

Neither is a Phase 8 design change — both are correctness bugs in Phase
5/6's own mechanisms that a single-write verification pass doesn't
exercise. See PLAN.md's Phase 8 implementation notes for the full
diagnosis.

## Post-MVP hardening (2026-10 audit)
An audit after Phase 8 led to: every data route under `/v1` behind an
optional API key, with debug-only demo/admin routes and API docs; rate
limiting that can't be bypassed with arbitrary keys; CORS headers on 429s
and 500s; a 503 (not a silent 200) from `/chat` when the database is down;
and DB-backed integration tests in `backend/tests/integration/` (they skip
without Postgres — `REQUIRE_DB=1` makes that a failure). See README's Tests
section.

## Stack (decided)
- Backend: Python, FastAPI, PostgreSQL + pgvector, SQLAlchemy/Alembic,
  sentence-transformers, scikit-learn RandomForest + SHAP, networkx
- Frontend: React + Vite + TypeScript, TanStack Query, `@xyflow/react` +
  `elkjs`, recharts, Tailwind

## Patent / novelty framing
Do not position this as a novel patentable invention without re-checking
prior art first. A 2026-07 search found close, recent (Mar–Jul 2026)
academic work covering the core mechanisms: MemLineage (Merkle+DAG lineage
gate), MemAudit (causal-attribution rollback auditing), A-MAC (interpretable
admission scoring), TMA-NM (corroboration-gated authority + corroboration-
laundering attacks). Full citations in docs/DESIGN.md's "Related Work"
section. Current pitch framing: RecoverMem is a coherent, demoable
*integration* of these ideas, not a novel primitive.
