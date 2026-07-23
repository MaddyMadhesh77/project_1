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
