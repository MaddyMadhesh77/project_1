from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import RollbackEvent, RollbackOutcome
from app.services import rollback, versioning

router = APIRouter(tags=["rollback"])


class RollbackRequest(BaseModel):
    triggered_by: str = Field(default="admin", max_length=200)


class NodeOutcomeOut(BaseModel):
    version_id: uuid.UUID
    memory_id: uuid.UUID
    text: str
    outcome: str  # kept | reverted | removed | superseded
    new_version_id: uuid.UUID
    trust_score: float
    reason: str


class RollbackResponse(BaseModel):
    rollback_id: uuid.UUID
    root_version_id: uuid.UUID
    affected: list[NodeOutcomeOut]
    triggered_by: str
    started_at: datetime
    completed_at: datetime | None
    merkle_root: str


@router.post("/rollback/{version_id}", response_model=RollbackResponse)
async def trigger_rollback(
    version_id: uuid.UUID,
    body: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RollbackResponse:
    """DESIGN.md 6.10: mark `version_id` poisoned and dependency-aware-recover
    everything derived from it. Runs synchronously (like /integrity/verify) --
    the animated "Finding descendants..." sequence in Rollback.tsx is a
    client-side staged reveal of this response, not real server-side
    progress; the demo-scale graphs here resolve in well under a second.
    """
    try:
        result = await rollback.run_rollback(
            db, poisoned_version_id=version_id, triggered_by=body.triggered_by, settings=settings
        )
    except versioning.ConcurrentUpdateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await db.commit()

    return RollbackResponse(
        rollback_id=result.rollback_id,
        root_version_id=result.root_version_id,
        affected=[
            NodeOutcomeOut(
                version_id=o.version_id,
                memory_id=o.memory_id,
                text=o.text,
                outcome=o.outcome,
                new_version_id=o.new_version_id,
                trust_score=o.trust_score,
                reason=o.reason,
            )
            for o in result.affected
        ],
        triggered_by=result.triggered_by,
        started_at=result.started_at,
        completed_at=result.completed_at,
        merkle_root=result.merkle_root,
    )


@router.get("/rollback/{rollback_id}", response_model=RollbackResponse)
async def get_rollback(rollback_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> RollbackResponse:
    """Fetch a past rollback run's persisted result, e.g. for re-display
    after a page refresh."""
    event = await db.get(RollbackEvent, rollback_id)
    if event is None:
        raise HTTPException(status_code=404, detail="rollback event not found")

    # Real FK/typed columns now (rollback_outcomes), not a JSONB blob -- no
    # per-row parsing/validation needed, the DB already guarantees the shape.
    outcome_rows = (
        await db.execute(
            sa.select(RollbackOutcome)
            .where(RollbackOutcome.rollback_id == rollback_id)
            .order_by(RollbackOutcome.outcome_index)
        )
    ).scalars().all()

    return RollbackResponse(
        rollback_id=event.rollback_id,
        root_version_id=event.root_version_id,
        affected=[
            NodeOutcomeOut(
                version_id=o.version_id,
                memory_id=o.memory_id,
                text=o.text,
                outcome=o.outcome,
                new_version_id=o.new_version_id,
                trust_score=float(o.trust_score),
                reason=o.reason,
            )
            for o in outcome_rows
        ],
        triggered_by=event.triggered_by,
        started_at=event.started_at,
        completed_at=event.completed_at,
        merkle_root=event.merkle_root_hash or "",
    )
