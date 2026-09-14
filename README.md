# RecoverMem

A security middleware layer between an AI agent's LLM and its long-term
memory store: trust-scores every candidate memory before it's persisted,
keeps full version/provenance history, tamper-evidences the store with a
Merkle tree, tracks derivation dependencies between memories, and can
automatically roll back everything downstream of a memory later found to
be poisoned.

See [docs/DESIGN.md](docs/DESIGN.md) for the full architecture, data model,
API surface, and build roadmap, and [docs/PLAN.md](docs/PLAN.md) for the
phased build plan and current status.

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
alembic upgrade head        # once migrations exist (Phase 1+)
uvicorn app.main:app --reload

# 4. Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

- Backend: http://localhost:8000 (`/health` should return `{"status": "ok"}`)
- Frontend: http://localhost:5173 (`/` chat, `/admin/*` dashboard)

Don't run the backend with `uvicorn ... --workers N` (N > 1) without
accounting for it first: each worker is a separate process that loads its
own full copy of the sentence-transformers embedding model
(`app/services/embedding.py`) independently -- N workers means N times the
model's memory footprint, with no sharing between them. A single worker's
async event loop already serves many concurrent requests fine; scale
throughput by running multiple single-worker instances behind a load
balancer (or extracting embedding inference into its own service) rather
than by adding `--workers`.
