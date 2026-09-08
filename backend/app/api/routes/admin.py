from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.services import demo_seed
from app.services import graph as graph_service

router = APIRouter(tags=["admin"])

# Every table the memory pipeline writes to, in no particular order --
# RESTART IDENTITY CASCADE handles both the memories.current_version_id FK
# cycle and every child table's FK to memories/memory_versions in one
# statement, which is exactly the "drop the DB and re-run migrations" manual
# step bugs.md #11 wanted an endpoint for.
_TABLES = [
    "memories",
    "memory_versions",
    "provenance",
    "dependency_edges",
    "trust_events",
    "merkle_roots",
    "rollback_events",
    "rollback_outcomes",
]


class ResetResponse(BaseModel):
    truncated_tables: list[str]
    seeded_lines: list[str]


@router.post("/admin/reset", response_model=ResetResponse)
async def reset_demo(
    db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings)
) -> ResetResponse:
    """Demo-only (bugs.md #11: "no concept of reset to clean demo state").
    Truncates every memory-pipeline table and re-seeds the DESIGN.md §9
    flow-2 chain via the same app/services/demo_seed.py logic
    scripts/seed_demo.py uses, so a demo can return to a known-clean state
    without dropping the database and re-running migrations by hand. Only
    registered when settings.debug is true (see create_app() in main.py) --
    just as destructive as app/api/routes/attack.py's endpoints, only
    pointed at every row instead of one.
    """
    await db.execute(text(f"TRUNCATE TABLE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    graph_service.invalidate_cache()

    seeded_lines = await demo_seed.seed_demo(db, settings) or []
    await db.commit()

    return ResetResponse(truncated_tables=_TABLES, seeded_lines=seeded_lines)
