from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.ml import train
from app.models import MemoryVersion
from app.services import trust_engine

router = APIRouter(tags=["trust"])
# Retraining rewrites app/ml/model.pkl on disk, which every later scoring call
# then unpickles -- operator-only, so main.py registers this router in debug
# mode only, like the attack/admin routes.
retrain_router = APIRouter(tags=["trust"])


class TrustOut(BaseModel):
    version_id: uuid.UUID
    trust_score: float
    trust_breakdown: dict
    decision: str


class ModelStatusOut(BaseModel):
    # rule_only: RF not loaded or gated off. rf_bootstrap: synthetic-trained
    # RF allowed by ML_BOOTSTRAP_ON_SYNTHETIC. rf_real: enough real samples.
    mode: Literal["rule_only", "rf_bootstrap", "rf_real"]
    model_loaded: bool
    n_samples: int
    n_real_samples: int
    trained_at: str | None
    min_training_samples: int
    bootstrap_on_synthetic: bool
    rf_blend_weight: float


class RetrainOut(BaseModel):
    n_samples: int
    n_synthetic_samples: int
    n_real_samples: int
    n_safe: int
    n_poisoned: int
    train_accuracy: float
    trained_at: str
    signed: bool


@retrain_router.post("/trust/retrain", response_model=RetrainOut)
async def retrain_model() -> RetrainOut:
    """Manual retrain trigger, so retraining doesn't require shell access
    to run `python -m app.ml.train`. Runs the same training
    pipeline as `python -m app.ml.train`, in-process -- picks up any real
    trust_events/rollback_events accumulated since the last run, rewrites
    app/ml/model.pkl, and clears trust_engine's in-process model cache so
    the next scoring call sees it immediately. Still a manual trigger, not
    an automatic retrain loop -- see PLAN.md Phase 7 notes for why that's
    deliberate.
    """
    try:
        summary = await train.run_training()
    except train.TrainingDataMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RetrainOut(**summary)


# Declared before /trust/{version_id} so "model" isn't parsed as a version id.
@router.get("/trust/model", response_model=ModelStatusOut)
async def get_model_status(settings: Settings = Depends(get_settings)) -> ModelStatusOut:
    """Which scorer new candidates currently get, so the UI can label SHAP
    breakdowns as bootstrap (synthetic-trained) vs. learned from real outcomes."""
    return ModelStatusOut(**trust_engine.model_status(settings))


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
