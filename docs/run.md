Yes — that was the design goal from day one (PLAN.md's open question #2: "local laptop only, no deployment target"). Per README.md:


cp .env.example .env
docker-compose up -d          # Postgres + pgvector

cd backend
python -m venv .venv && ./.venv/Scripts/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload  # http://localhost:8000

cd frontend
npm install
npm run dev                    # http://localhost:5173
Then in a browser: / is the chat interface, /admin/* is the dashboard (memories, memory detail + dependency graph, integrity, rollback, analytics, logs). backend/scripts/seed_demo.py pre-seeds the "likes Python → recommend Django → recommend FastAPI" chain so the rollback/graph demo has something to act on immediately.

DESIGN.md §9 lays out 5 concrete demo beats you can actually click through and see: poison-and-reject live in chat, dependency-aware rollback with animated per-node outcomes, tamper-detection via Merkle mismatch, SHAP explainability breakdown, and semantic search. All of it runs on your laptop, no cloud dependency required (the TemplatedLLMClient default needs no API key at all).





Before you start
Both servers are already running on your machine right now, and the DB is freshly seeded:

Backend: http://localhost:8000 (/health → {"status":"ok"})
Frontend: http://localhost:5173
Open http://localhost:5173 in a browser. / is the chat UI, /admin is the dashboard (nav: Overview, Memories, Integrity, Rollback, Analytics, Logs).

One important thing I discovered while rehearsing this: the "Rollback" page always targets a memory's current version. If you contradict "preference: Python" in chat first, it stops being the trusted root the Django/FastAPI recommendations depend on, and the rollback cascade demo will fizzle (1 node instead of 3). So do Rollback before you do the chat-contradiction demo — order below is safe.

Step 1 — Semantic search (proves hybrid retrieval works)
Go to Memories page → use the search box, or curl:


GET /search?q=backend frameworks
Real output you'll see: 3 hits ranked by similarity — goal: learn Django (0.33), preference: Python (0.15), goal: learn FastAPI (0.12), each with its trust score.

Step 2 — Explainability (trust breakdown)
Memories → click into "preference: Python" (trust 86.0, trusted).
Real output: a breakdown panel with bars for baseline (50.1), contradiction (+27.5), similarity (+8.9), has_match (+8.3), prior_trust_score (+4.8), source_reliability (+3.0), memory_age_days (+3.4), corroboration_count (−6.0) — summing to 86.0. This is a real SHAP/rule breakdown, not a mock.

Step 3 — Dependency graph
On that same memory's page, click Graph.
Real output: 3 nodes, 2 arrows — preference: Python → goal: learn Django → goal: learn FastAPI.

Step 4 — Rollback cascade (the centerpiece)
Go to Rollback page → section 3 "Rollback / recover" → pick "preference: Python" from the dropdown → "Mark poisoned & recover".
Real output: all 3 nodes animate in, each outcome = Removed, reason = "solely dependent on the poisoned version; no prior version to revert to", new trust 0.0 each, and a fresh Merkle root is shown. This is the "poison the root, watch everything downstream get purged since nothing else corroborates it" story.

Step 5 — Tamper detection
Go to Chat (/) and type: I live in Bangalore → stores cleanly at trust 86.0.
Then Rollback page → section 2 "Tamper with the database" → pick that memory → "Tamper DB" (simulates a rogue DBA editing the row directly, bypassing your API).
Then go to Integrity page → "Verify Integrity".
Real output: tampered: true, the exact version_id you just tampered is named as the mismatch, expected root ≠ actual root. This is the Merkle tree catching an out-of-band edit your API never touched.

Step 6 — Poison + reject live (contradiction quarantine)
Back on Chat, type: I hate Python.
Real output: stored as preference: not Python, trust 36.3, decision reject — shows up as quarantined/low-trust on the Memories page, contradicting the earlier "likes Python" statement (now already rolled back, but the contradiction logic still catches it cleanly).

Step 7 (bonus) — Analytics & Logs
Analytics page: status counts (trusted/quarantined/rolled_back) and a store/review/reject/rollback trend chart. Logs page: paginated trust-event feed — you'll see every action from steps 1–6 listed with timestamps, decisions, and scores. Good for closing the demo with "here's the audit trail."

Resetting for a real run in front of your guide
Rehearsing consumes the seed data (step 4 deletes the demo chain, step 6 quarantines Python). To get back to the pristine starting state before the real thing:


docker exec recovermem-postgres psql -U recovermem -d recovermem -c "TRUNCATE TABLE rollback_events, merkle_roots, dependency_edges, trust_events, provenance, memory_versions, memories RESTART IDENTITY CASCADE;"
cd backend && ./.venv/Scripts/python.exe scripts/seed_demo.py
I've already left the DB in this clean, reseeded state for you right now — you can walk through steps 1–7 immediately.