from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.params import PageLimit
from app.db.session import get_db
from app.models import MerkleRoot
from app.services import merkle

router = APIRouter(tags=["integrity"])


class RowMismatchOut(BaseModel):
    version_id: uuid.UUID
    memory_id: uuid.UUID


class VerifyResponse(BaseModel):
    tampered: bool
    row_mismatches: list[RowMismatchOut]
    orphaned_version_ids: list[uuid.UUID]
    root_mismatch: bool
    expected_root: str | None
    actual_root: str
    leaf_count: int


class MerkleRootOut(BaseModel):
    root_id: uuid.UUID
    root_hash: str
    leaf_count: int
    computed_at: datetime


@router.get("/integrity/verify", response_model=VerifyResponse)
async def verify_integrity(db: AsyncSession = Depends(get_db)) -> VerifyResponse:
    """DESIGN.md 6.8 Verify Integrity -- recompute + compare, read-only (no
    write path taken here even when tampering is found). GET, not POST:
    this performs no mutation, so it belongs in the
    cacheable/retryable/prefetchable half of HTTP -- and on the client,
    TanStack Query only treats GETs as queries it can cache and auto-retry."""
    result = await merkle.verify_integrity(db)
    return VerifyResponse(
        tampered=result.tampered,
        row_mismatches=[
            RowMismatchOut(version_id=m.version_id, memory_id=m.memory_id) for m in result.row_mismatches
        ],
        orphaned_version_ids=result.orphaned_version_ids,
        root_mismatch=result.root_mismatch,
        expected_root=result.expected_root,
        actual_root=result.actual_root,
        leaf_count=result.leaf_count,
    )


@router.get("/integrity/history", response_model=list[MerkleRootOut])
async def get_integrity_history(limit: PageLimit = 20, db: AsyncSession = Depends(get_db)) -> list[MerkleRootOut]:
    # sequence_number, not computed_at -- see migration 8b2e5f6a1c9d (computed_at
    # is transaction time, identical across a multi-write transaction like a
    # rollback, so it can't recover true insertion order on its own).
    rows = (
        await db.execute(select(MerkleRoot).order_by(MerkleRoot.sequence_number.desc()).limit(limit))
    ).scalars().all()
    return [
        MerkleRootOut(root_id=r.root_id, root_hash=r.root_hash, leaf_count=r.leaf_count, computed_at=r.computed_at)
        for r in rows
    ]
