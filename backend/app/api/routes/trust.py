from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.ml import train
from app.models import MemoryVersion

router = APIRouter(tags=["trust"])


class TrustOut(BaseModel):
    version_id: uuid.UUID
    trust_score: float
    trust_breakdown: dict
    decision: str


class RetrainOut(BaseModel):
    n_samples: int
    n_synthetic_samples: int
    n_real_samples: int
    n_safe: int
    n_poisoned: int
    train_accuracy: float
    trained_at: str
    signed: bool


@router.post("/trust/retrain", response_model=RetrainOut)
async def retrain_model() -> RetrainOut:
    """Manual retrain trigger (bugs.md #10: "train.py must be run manually.
    There's no endpoint ... to trigger retraining"). Runs the same training
    pipeline as `python -m app.ml.train`, in-process -- picks up any real
    trust_events/rollback_events accumulated since the last run, rewrites
    app/ml/model.pkl, and clears trust_engine's in-process model cache so
    the next scoring call sees it immediately. Still a manual trigger, not
    an automatic retrain loop -- see PLAN.md Phase 7 notes for why that's
    deliberate.
    """
    summary = await train.run_training()
    return RetrainOut(**summary)


@router.get("/trust/{version_id}", response_model=TrustOut)
async def get_trust(version_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> TrustOut:
    version = await db.get(MemoryVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="version not found")

    return TrustOut(
        version_id=version.version_id,
        trust_score=float(version.trust_score),
        trust_breakdown=version.trust_breakdown,
        decision=version.decision,
    )
