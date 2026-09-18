# RecoverMem

A security middleware layer between an AI agent's LLM and its long-term
memory store: trust-scores every candidate memory before it's persisted,
keeps full version/provenance history, tamper-evidences the store with a
Merkle tree, tracks derivation dependencies between memories, and can
automatically roll back everything downstream of a memory later found to
be poisoned.

See [docs/DESIGN.md](docs/DESIGN.md) for the full architecture, data model,
API surface, and build roadmap, [docs/PLAN.md](docs/PLAN.md) for the
phased build plan and current status, [docs/run.md](docs/run.md) for the
demo walkthrough, and [docs/README.md](docs/README.md) for what every other
doc is for.

## Running locally

Requires Docker, Python 3.11+, and Node 20+.

```bash
# 1. Env
cp .env.example .env

# 2. Postgres (pgvector-enabled), on host port 5433 by default -- see
#    .env's POSTGRES_PORT if you need to change it (e.g. to avoid clashing
#    with a Postgres install already using 5432 on your machine)
docker-compose up -d

# 3. Backend
cd backend
python -m venv .venv
./.venv/Scripts/activate   # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_demo.py # demo chain: likes Python -> Django -> FastAPI
python -m app.ml.train      # optional: SHAP trust breakdowns (see .env's ML_BOOTSTRAP_ON_SYNTHETIC)
uvicorn app.main:app --reload

# 4. Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

- Backend: http://localhost:8000 (`/health` should return `{"status": "ok"}`)
- Frontend: http://localhost:5173 (`/` chat, `/admin/*` dashboard)

## Tests

```bash
cd backend
pytest
```

- `tests/unit/` needs nothing running.
- `tests/integration/` runs against real Postgres + pgvector (the
  docker-compose service, in a separate `recovermem_test` database that the
  fixtures create and migrate automatically). Each test starts from empty
  tables. If Postgres isn't reachable these tests are **skipped**, not
  failed; set `REQUIRE_DB=1` (e.g. in CI) to make that a failure, and
  `TEST_DATABASE_URL` to point at a different server.

## Deployment note

Don't run the backend with `uvicorn ... --workers N` (N > 1) without
accounting for it first: each worker is a separate process that loads its
own full copy of the sentence-transformers embedding model
(`app/services/embedding.py`) independently -- N workers means N times the
model's memory footprint, with no sharing between them. A single worker's
async event loop already serves many concurrent requests fine; scale
throughput by running multiple single-worker instances behind a load
balancer (or extracting embedding inference into its own service) rather
than by adding `--workers`.
