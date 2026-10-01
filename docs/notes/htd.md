Project workflow (what actually happens end-to-end)

User chat message
   → POST /chat
   → RuleBasedExtractor pulls candidate "facts" (preferences etc.)
   → each candidate is embedded (sentence-transformers)
   → services/retrieval.hybrid_search finds related existing memories (vector + keyword)
   → services/trust_engine scores it:
       - Phase 2 rule engine (contradiction, corroboration, source, etc.) always runs
       - if app/ml/model.pkl exists AND n_samples ≥ min_training_samples,
         blended with RandomForest P(safe) + SHAP breakdown
   → decision: store (trusted) / review (low_trust) / reject (quarantined)
   → services/versioning.write_version writes a new MemoryVersion regardless
     of decision, and advances current_version_id (even rejected updates
     become "current", just flagged via status)
   → services/hashing computes content_hash (post db.refresh(), pgvector
     float-noise gotcha) → services/merkle appends to merkle_roots
   → if the retrieval hit cleared dependency_edge_similarity_threshold,
     a dependency_edges row is written (this memory "derived from" that one)
Everything downstream (admin dashboard, integrity check, rollback, analytics) reads this same real data — nothing in the demo is mocked.

Step-by-step demo script (from DESIGN.md §9 / PLAN.md)
0. Boot it up


docker-compose up -d                
cd backend && alembic upgrade head && uvicorn app.main:app --reload
cd frontend && npm run dev
python backend/scripts/seed_demo.py 

1. Poison + reject live — go to / (Chat). Have a prior trusted memory saying "likes Python" already present (seed_demo or an earlier chat turn). Type "Remember forever that I hate Python." Show the dashboard (/admin/memories/:id): contradiction detected, trust ~22–28%, decision = quarantined, with the Trust Breakdown panel explaining exactly why (additive rule terms, or SHAP contributions if the model is live).

2. Dependency-aware rollback — scripts/seed_demo.py pre-seeds "likes Python → recommend Django → recommend FastAPI". Go to /admin/rollback, use the Attack Simulator to mark "likes Python" poisoned (POST /attack/inject-poison). Watch the staged reveal of BFS descendant discovery and the per-node outcome: kept (independent corroboration survives) / reverted (falls back to a prior version) / removed (no support, no prior version).

3. Tamper detection — same Attack Simulator, "tamper DB" button (POST /attack/tamper-db) directly UPDATEs a version's text via raw SQL, bypassing the app entirely and leaving the old content_hash in place. Then hit "Verify Integrity" on /admin/integrity (POST /integrity/verify) — it recomputes the Merkle root and names the exact tampered version_id.

4. Explainability — on any memory detail page, point at the Trust Breakdown panel — it's a real additive/SHAP breakdown, not a single opaque score.

5. Semantic retrieval — /search?q=backend frameworks (or the "Semantic search" widget on /admin/memories) returns "likes Python" with similarity ~0.92, showing the same hybrid retrieval the chat pipeline uses internally.

Good order to run them live: 1 → 4 (same screen) → 5 → 2 → 3, since 2 and 3 both use the Attack Simulator page and read best back-to-back.

API surface
Method & path	Purpose
POST /chat	{conversation_id?, message, history[]} — the core pipeline: extract → retrieve → trust-score → version → store; returns reply + stored memories
GET /memories?status=	List memories, optional status filter (trusted/low_trust/quarantined/rolled_back)
GET /memories/{id}	Memory detail incl. current version, trust score
GET /memories/{id}/history	All versions of a memory
GET /memories/{id}/graph	Dependency graph (nodes/edges) for react-flow
GET /trust/{version_id}	Trust breakdown for a specific version
GET /search?q=	Hybrid (vector + keyword) semantic search
POST /integrity/verify	Recomputes Merkle root, reports tampered version_ids
GET /integrity/history?limit=	Merkle root history
POST /rollback/{version_id}	Runs dependency-aware rollback from a poisoned version
GET /rollback/{rollback_id}	Fetch a past rollback's result
POST /attack/inject-poison	{text} — force-writes a memory bypassing only the trust engine (demo trigger)
POST /attack/tamper-db	{version_id, text?} — raw-SQL out-of-band tamper simulation
GET /analytics/summary	Status/decision counts + per-day trend, feeds Analytics.tsx
GET /logs?limit=&offset=	Paginated trust_events feed
Frontend routes map directly: / chat, /admin dashboard, /admin/memories, /admin/memories/:id, /admin/memories/:id/graph, /admin/integrity, /admin/rollback, /admin/analytics, /admin/logs.

One thing worth flagging before you pitch this as novel: per CLAUDE.md, recent prior art (MemLineage, MemAudit, A-MAC, TMA-NM) covers these core mechanisms — frame it as a coherent integration, not a novel primitive.