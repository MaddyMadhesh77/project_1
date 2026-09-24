from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.params import PageLimit, PageOffset
from app.db.session import get_db
from app.models import DependencyEdge, Memory, MemoryVersion, RollbackEvent, RollbackOutcome
from app.services import graph as graph_service

router = APIRouter(tags=["memories"])


class MemoryOut(BaseModel):
    memory_id: uuid.UUID
    status: str
    current_version_id: uuid.UUID | None
    text: str | None
    trust_score: float | None
    decision: str | None
    version_count: int


class MemoryDetailOut(MemoryOut):
    trust_breakdown: dict | None
    content_hash: str | None


class MemoriesPageOut(BaseModel):
    items: list[MemoryOut]
    total: int


class MemoryVersionOut(BaseModel):
    version_id: uuid.UUID
    version_number: int
    text: str
    trust_score: float
    trust_breakdown: dict
    decision: str
    content_hash: str
    is_active: bool
    created_at: datetime


class MemoryHistoryPageOut(BaseModel):
    items: list[MemoryVersionOut]
    total: int


class GraphNodeOut(BaseModel):
    version_id: uuid.UUID
    memory_id: uuid.UUID
    text: str
    trust_score: float
    status: str
    is_current: bool


class GraphEdgeOut(BaseModel):
    parent_version_id: uuid.UUID
    child_version_id: uuid.UUID
    relation_type: str


class MemoryGraphOut(BaseModel):
    root_version_id: uuid.UUID
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class MemoryRollbackOut(BaseModel):
    rollback_id: uuid.UUID
    version_id: uuid.UUID
    outcome: str  # kept | reverted | removed
    new_version_id: uuid.UUID
    trust_score: float
    reason: str
    triggered_by: str
    started_at: datetime


def _version_counts_subquery():
    # A single GROUP BY over all versions, joined in once, instead of a
    # correlated subquery re-evaluated per Memory row (effectively N+1 at
    # Postgres's query-execution level once the memories list gets large).
    return (
        select(MemoryVersion.memory_id, func.count(MemoryVersion.version_id).label("version_count"))
        .group_by(MemoryVersion.memory_id)
        .subquery()
    )


@router.get("/memories", response_model=MemoriesPageOut)
async def list_memories(
    status: str | None = None, limit: PageLimit = 50, offset: PageOffset = 0, db: AsyncSession = Depends(get_db)
) -> MemoriesPageOut:
    # Unbounded before this: a memory table with hundreds of
    # rows returned the full table on every load. limit/offset + a total
    # count mirror GET /logs's existing paginated shape.

    count_stmt = select(func.count()).select_from(Memory)
    if status:
        count_stmt = count_stmt.where(Memory.status == status)
    total = (await db.execute(count_stmt)).scalar_one()

    counts = _version_counts_subquery()
    stmt = (
        select(Memory, MemoryVersion, func.coalesce(counts.c.version_count, 0))
        .outerjoin(MemoryVersion, Memory.current_version_id == MemoryVersion.version_id)
        .outerjoin(counts, counts.c.memory_id == Memory.memory_id)
        .order_by(Memory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        stmt = stmt.where(Memory.status == status)

    rows = (await db.execute(stmt)).all()
    items = [
        MemoryOut(
            memory_id=memory.memory_id,
            status=memory.status,
            current_version_id=memory.current_version_id,
            text=version.text if version else None,
            trust_score=float(version.trust_score) if version else None,
            decision=version.decision if version else None,
            version_count=count,
        )
        for memory, version, count in rows
    ]
    return MemoriesPageOut(items=items, total=total)


@router.get("/memories/{memory_id}", response_model=MemoryDetailOut)
async def get_memory(memory_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> MemoryDetailOut:
    memory = await db.get(Memory, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="memory not found")

    version = await db.get(MemoryVersion, memory.current_version_id) if memory.current_version_id else None
    count = (
        await db.execute(select(func.count(MemoryVersion.version_id)).where(MemoryVersion.memory_id == memory_id))
    ).scalar_one()

    return MemoryDetailOut(
        memory_id=memory.memory_id,
        status=memory.status,
        current_version_id=memory.current_version_id,
        text=version.text if version else None,
        trust_score=float(version.trust_score) if version else None,
        decision=version.decision if version else None,
        version_count=count,
        trust_breakdown=version.trust_breakdown if version else None,
        content_hash=version.content_hash if version else None,
    )


@router.get("/memories/{memory_id}/history", response_model=MemoryHistoryPageOut)
async def get_memory_history(
    memory_id: uuid.UUID, limit: PageLimit = 50, offset: PageOffset = 0, db: AsyncSession = Depends(get_db)
) -> MemoryHistoryPageOut:
    memory = await db.get(Memory, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="memory not found")

    # Unbounded before this: a memory with hundreds of versions
    # returned every row on every page load.

    total = (
        await db.execute(
            select(func.count()).select_from(MemoryVersion).where(MemoryVersion.memory_id == memory_id)
        )
    ).scalar_one()

    versions = (
        await db.execute(
            select(MemoryVersion)
            .where(MemoryVersion.memory_id == memory_id)
            .order_by(MemoryVersion.version_number.asc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    items = [
        MemoryVersionOut(
            version_id=v.version_id,
            version_number=v.version_number,
            text=v.text,
            trust_score=float(v.trust_score),
            trust_breakdown=v.trust_breakdown,
            decision=v.decision,
            content_hash=v.content_hash,
            is_active=v.is_active,
            created_at=v.created_at,
        )
        for v in versions
    ]
    return MemoryHistoryPageOut(items=items, total=total)


@router.get("/memories/{memory_id}/graph", response_model=MemoryGraphOut)
async def get_memory_graph(memory_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> MemoryGraphOut:
    """Ancestor+descendant subgraph around a memory's current version
    (DESIGN.md 6.9 / 7). Reuses services/graph.py's networkx wrapper, which
    Phase 6's rollback engine will also BFS over."""
    memory = await db.get(Memory, memory_id)
    if memory is None or memory.current_version_id is None:
        raise HTTPException(status_code=404, detail="memory not found")

    root_version_id = memory.current_version_id
    dep_graph = await graph_service.load_graph(db)
    related_version_ids = (
        {root_version_id}
        | graph_service.ancestors(dep_graph, root_version_id)
        | graph_service.descendants(dep_graph, root_version_id)
    )

    rows = (
        await db.execute(
            select(MemoryVersion, Memory)
            .join(Memory, Memory.memory_id == MemoryVersion.memory_id)
            .where(MemoryVersion.version_id.in_(related_version_ids))
        )
    ).all()
    nodes = [
        GraphNodeOut(
            version_id=version.version_id,
            memory_id=version.memory_id,
            text=version.text,
            trust_score=float(version.trust_score),
            status=owner.status,
            is_current=(owner.current_version_id == version.version_id),
        )
        for version, owner in rows
    ]

    edge_rows = (
        await db.execute(
            select(DependencyEdge).where(
                DependencyEdge.parent_version_id.in_(related_version_ids),
                DependencyEdge.child_version_id.in_(related_version_ids),
            )
        )
    ).scalars().all()
    edges = [
        GraphEdgeOut(
            parent_version_id=edge.parent_version_id,
            child_version_id=edge.child_version_id,
            relation_type=edge.relation_type,
        )
        for edge in edge_rows
    ]

    return MemoryGraphOut(root_version_id=root_version_id, nodes=nodes, edges=edges)


@router.get("/memories/{memory_id}/rollbacks", response_model=list[MemoryRollbackOut])
async def get_memory_rollbacks(memory_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[MemoryRollbackOut]:
    """Every rollback run that touched this memory, most recent first --
    answered via the indexed rollback_outcomes.memory_id FK (see
    app/models/rollback_outcome.py) rather than scanning
    rollback_events.affected_version_ids as JSON, which had no index to
    support this query at all.
    """
    memory = await db.get(Memory, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="memory not found")

    rows = (
        await db.execute(
            select(RollbackOutcome, RollbackEvent.triggered_by, RollbackEvent.started_at)
            .join(RollbackEvent, RollbackEvent.rollback_id == RollbackOutcome.rollback_id)
            .where(RollbackOutcome.memory_id == memory_id)
            .order_by(RollbackEvent.started_at.desc())
        )
    ).all()

    return [
        MemoryRollbackOut(
            rollback_id=outcome.rollback_id,
            version_id=outcome.version_id,
            outcome=outcome.outcome,
            new_version_id=outcome.new_version_id,
            trust_score=float(outcome.trust_score),
            reason=outcome.reason,
            triggered_by=triggered_by,
            started_at=started_at,
        )
        for outcome, triggered_by, started_at in rows
    ]
