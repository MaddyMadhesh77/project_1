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
Phases 0-3 complete — see [docs/PLAN.md](docs/PLAN.md) for the checklist,
per-phase demo checkpoints, and the implementation notes/deviations
recorded under Phases 2 and 3. Phase 4 (dependency graph) not started.

Trust gating is real as of Phase 2: every extracted candidate is scored
by a deterministic additive rule engine (`services/trust_engine.py`)
against hybrid retrieval + feature engineering, and lands as
store/review/reject (`memories.status` = trusted/low_trust/quarantined).
Contradictory updates version instead of overwriting — `current_version_id`
always advances to the newest version regardless of decision (so a
rejected update still becomes "current," flagged via status, with prior
versions intact in history — see PLAN.md Phase 2's implementation notes
for why). The admin dashboard (`/admin`, `/admin/memories`,
`/admin/memories/:id`) reads this real data — no mocks. No RF/SHAP layer
yet (Phase 7); the rule scorer is authoritative. No dependency graph,
Merkle integrity, or rollback engine yet (Phases 4-6).

## Stack (decided)
- Backend: Python, FastAPI, PostgreSQL + pgvector, SQLAlchemy/Alembic,
  sentence-transformers, scikit-learn RandomForest + SHAP, networkx
- Frontend: React + Vite + TypeScript, TanStack Query, react-flow, recharts,
  Tailwind

## Patent / novelty framing
Do not position this as a novel patentable invention without re-checking
prior art first. A 2026-07 search found close, recent (Mar–Jul 2026)
academic work covering the core mechanisms: MemLineage (Merkle+DAG lineage
gate), MemAudit (causal-attribution rollback auditing), A-MAC (interpretable
admission scoring), TMA-NM (corroboration-gated authority + corroboration-
laundering attacks). Full citations in docs/DESIGN.md's "Related Work"
section. Current pitch framing: RecoverMem is a coherent, demoable
*integration* of these ideas, not a novel primitive.
