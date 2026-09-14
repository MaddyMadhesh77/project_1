Phase 0 and Phase 1 are both implemented and verified end-to-end. Summary:

Phase 0 (scaffold): git repo, docker-compose Postgres+pgvector, FastAPI skeleton with /health, Alembic wired to Settings, Vite+React+TS+Tailwind frontend with / and /admin/* stub routes. Found and worked around a port conflict — a native Postgres install already owned 5432, so the container now uses 5433 (documented in .env.example and PLAN.md).

Phase 1 (core loop): memories/memory_versions/provenance tables (exact §5 DDL, migration applied), LLMClient (Templated + Claude), RuleBasedExtractor, EmbeddingService, POST /chat and GET /memories[/{id}], and a real Chat.tsx wired through lib/api.ts/lib/queries.ts. Verified via curl through the actual Vite dev proxy: "I live in Bangalore and I like Python" → two memory rows, trust_score=100, decision=store. Also caught and fixed a greedy-regex extraction bug along the way, and pre-computed content_hash now (needed since that column is NOT NULL, and PLAN.md itself flags this as easy to forget).

Both are checked off with dated verification notes in docs/PLAN.md, and CLAUDE.md's status line is updated. One caveat: I didn't click-test the Chat UI in an actual browser (no browser-automation tool available this session) — I verified the same HTTP path via curl and confirmed tsc -b type-checks cleanly, but visual rendering is unverified.

Nothing is committed to git yet (left for you to review/commit). Phase 2 (hybrid retrieval + rule-based trust engine + versioning — the first phase with actual trust gating) is next whenever you want me to continue.

Phase 2 (backend trust gating) — services/retrieval.py (hybrid pgvector + tsvector search via RRF), services/features.py (7-feature vector + rule/LLM-judge contradiction detection), services/trust_engine.py (pure, unit-tested additive rule scorer), services/versioning.py (non-destructive version chains), and the trust_events table are all wired into POST /chat. Verified live against Postgres: "I like Python" → trust 72 (store) → repeated → trust 82 (store, self-corroboration) → "I hate Python" → trust 34.7 (reject/quarantined), with both prior versions intact in history. A second scenario (Bangalore→Mumbai) exercised the LLM-judge ambiguous-contradiction fallback, landing in review.

Phase 3 (admin dashboard) — AdminLayout, Dashboard, Memories, MemoryDetail pages plus StatTile/TrustBreakdownBars components, all reading real backend data (no mocks), nested under /admin/*. tsc -b && vite build passes clean.

Docs — docs/PLAN.md Phase 2/3 checkboxes ticked with verified demo-checkpoint notes and an "Implementation notes" section documenting design calls that weren't fully pinned down in DESIGN.md (e.g., why current_version_id advances even on reject — required for Phase 6's rollback to have something to revert from). CLAUDE.md's Status section now reflects Phases 0–3 done, Phase 4 next.

One honest gap, flagged in PLAN.md like Phase 1 was: no browser-automation tool was available this session, so the dashboard was verified functionally (correct data via the same network path the browser uses) but not visually click-tested.

Next up: Phase 4 (dependency graph).

Phase 4 (Dependency Graph): dependency_edges table + model, services/graph.py (networkx BFS/ancestor helpers, reusable by Phase 6's rollback engine), edge creation wired into the chat pipeline, GET /memories/{id}/graph, Graph.tsx + GraphView (react-flow/dagre), and an idempotent scripts/seed_demo.py that seeds the "likes Python → recommend Django → recommend FastAPI" chain the rule-based extractor can't produce on its own.

Phase 5 (Merkle Integrity): merkle_roots table + model, services/merkle.py (tree build + verify_integrity), root recomputed on every write, POST /integrity/verify + GET /integrity/history + POST /attack/tamper-db, and IntegrityCheck.tsx.

Notable bug found and fixed along the way: pgvector doesn't round-trip embedding floats bit-exactly through Postgres (~1e-9 noise per component), which made every legitimate row look "tampered" the first time verify_integrity read embeddings back from the DB — the first fix (rounding to 6 decimals) still failed probabilistically across 384-dimensional vectors, so I fixed it properly by hashing the embedding after a db.refresh(), guaranteeing write-time and verify-time hash identical bytes. Documented in PLAN.md and CLAUDE.md for future reference.

Verification: 26 backend unit tests pass, tsc -b && vite build is clean, and I exercised the full stack live (docker-compose Postgres, migrations, seed script, /chat, /integrity/verify, /attack/tamper-db) via curl, plus click-tested /admin/memories/:id/graph, /admin/memories/:id, and /admin/integrity in a real browser (Playwright + system Chrome) with zero console errors — screenshots confirmed the graph, breakdown bars, and integrity panel all render correctly. docs/PLAN.md and CLAUDE.md are updated with checked-off tasks, verification notes, and implementation deviations, matching the project's existing documentation style.

Confirmed — app/ml/ only has an empty __init__.py. No training data, no train.py, no model.pkl exist yet. That's all Phase 7 scope, which hasn't started.

To answer directly: no LLM training happens anywhere in this project, in any phase, including Phases 4 and 5. There are three separate ML-ish things in this codebase, and none of them involve training an LLM:

sentence-transformers/all-MiniLM-L6-v2 embeddings (used in Phase 1+, including by seed_demo.py in Phase 4) — this is a pre-trained model pulled from Hugging Face Hub at runtime (you saw the "Loading SentenceTransformer model..." log lines when I ran the seed script). It's used purely for inference — turning text into 384-dim vectors — never fine-tuned or trained. No dataset of ours involved.

ClaudeLLMClient (chat replies + judge_contradiction, Phase 1-2) — calls the Anthropic API for inference. Also never trained; it's an off-the-shelf API call. The default path (TemplatedLLMClient) doesn't even call an LLM — it's canned/deterministic string logic.

The RandomForest + SHAP "ML trust layer" — this is DESIGN.md §6.5/Phase 7, not implemented yet and not part of what I did today. It's also not an LLM — it's a small sklearn.ensemble.RandomForestClassifier. When that phase does happen, DESIGN.md's plan is a hand-authored synthetic dataset checked into backend/app/ml/data/synthetic_examples.json (safe/paraphrase examples + poisoned/contradiction examples over the feature schema), which doesn't exist yet — I'd write it by hand when that phase starts, not source it from anywhere external.

Phases 4 and 5 specifically (dependency graph, Merkle integrity) are pure data/graph/crypto engineering — networkx BFS over an edge table, and sha256 over row content. No model, no dataset, no training involved at all.

Summary
Implemented and verified Phases 6 and 7, both fully working end-to-end.

Phase 6 — Rollback Engine + Attack Simulator

rollback_events migration/model, services/rollback.py (BFS descendants via the existing graph service, re-validates each one with the poisoned ancestor excluded, branches to kept/reverted/removed, never mutates a row — always writes a new version)
POST /rollback/{version_id}, GET /rollback/{rollback_id}, POST /attack/inject-poison
Rollback.tsx admin page: inject poison / tamper DB / mark-poisoned-and-recover, with a staged animation over the real result
10 new unit tests on the pure decision logic; all three outcome branches (kept/reverted/removed) verified live against the real database, plus a full browser click-test with zero console errors
Phase 7 — ML Trust Layer (RandomForest + SHAP)

60-example hand-authored synthetic_examples.json, app/ml/train.py (trains on synthetic + real logged rollback outcomes, best-effort DB access)
trust_engine.py now blends the Phase 2 rule score with 100*P(safe) from a trained RF once model.pkl clears min_training_samples — trust_breakdown becomes real per-feature SHAP contributions once live
Re-ran the exact flow-1 demo script live through /chat: same store→reject narrative as Phase 2, now genuinely backed by shap.TreeExplainer, confirmed in the browser too
Along the way, found and fixed a real bug: training model.pkl locally silently broke Phase 2's own unit tests (they depended on incidental file-system state). Fixed by pointing them at the newly-extracted pure rule function.
Both docs/PLAN.md (checklists, verification notes, implementation-decision writeups in the existing style) and CLAUDE.md's status section are updated to reflect Phases 0–7 complete, Phase 8 next. All 43 backend tests pass, frontend builds clean, and the DB is left in a pristine seeded state. Nothing was committed — that's left for you to review.

One thing worth knowing: the backend (:8000) and frontend (:5173) dev servers are still running in the background from verification — let me know if you'd like me to stop them, or you can just leave them for poking at /admin/rollback yourself.



I've saved everything needed to a project memory file, so the next chat session will automatically have this context loaded — you don't need to paste anything. Here's the summary for your reference anyway:

What's done (Phase 8, all uncommitted)
Backend: /analytics/summary, /logs, /search routes + service + tests (48/48 passing)
Frontend: Analytics.tsx (recharts trend chart), Logs.tsx, semantic search widget on Memories page — all wired in, tsc -b && vite build pass, browser-verified with no console errors
Two real bugs found and fixed
pgvector's ivfflat index silently dropped search results at demo scale → dropped the index (migration 4f1a9b3c7d2e)
merkle_roots.computed_at used transaction time, causing false "tampered" reports after multi-write actions like rollback → added a real sequence column (migration 8b2e5f6a1c9d)
Phase 8 is implemented and the MVP is complete. What changed:

Backend — three new routes (GET /analytics/summary, GET /logs, GET /search), a new services/analytics.py with a pure, unit-tested trend-bucketing function, and two new Alembic migrations fixing real bugs found during rehearsal:

4f1a9b3c7d2e — dropped the ivfflat vector index, which was silently dropping relevant rows at this project's small demo scale (confirmed via EXPLAIN; this had been quietly degrading retrieval since Phase 2, not just the new /search route).
8b2e5f6a1c9d — added a real monotonic sequence_number to merkle_roots, fixing a false-tamper report that showed up right after a clean rollback (multiple roots written in one transaction shared a timestamp, and the old tiebreak on a random UUID could pick a stale one).
Frontend — Analytics.tsx (recharts trend chart, status-colored, dark-mode aware, with a table-view twin) and Logs.tsx (paginated trust_events feed), plus a small semantic-search widget added to Memories.tsx so flow 5 is browser-demoable too. Fixed a mid-build issue where the Logs page colored its badge by event type instead of the actual decision, which could show a green pill next to a rejected memory.

Rehearsal — ran all 5 §9 demo flows end-to-end against the real stack (poison+reject landed at 25.9% trust, inside the design doc's expected range; rollback, tamper detection, and search all confirmed working; a Docker Desktop crash mid-session was recovered from). 48→53 backend tests pass, frontend builds clean, zero browser console errors.

Docs — docs/PLAN.md's Phase 8 checklist and Definition of Done are fully checked with detailed implementation notes, and CLAUDE.md's status section now reflects all 8 phases complete, including notes on the two bugs for anyone touching retrieval or Merkle code later.

The database is left in a clean, freshly-seeded state ready for a demo run.