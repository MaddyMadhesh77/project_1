"""Helpers for writing memories straight through the real versioning
pipeline, with deterministic fake embeddings (no sentence-transformers load)."""
from __future__ import annotations

import random
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MemoryVersion
from app.models.memory_version import EMBEDDING_DIM
from app.services import versioning


def fake_embedding(seed: str) -> list[float]:
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(EMBEDDING_DIM)]


async def write(
    db: AsyncSession,
    text: str,
    *,
    memory_id: uuid.UUID | None = None,
    decision: str = "store",
    trust_score: float = 80.0,
) -> MemoryVersion:
    return await versioning.write_version(
        db,
        memory_id=memory_id,
        text=text,
        embedding=fake_embedding(text),
        trust_score=trust_score,
        trust_breakdown={"source": trust_score},
        decision=decision,
        provenance_fields={
            "conversation_id": uuid.uuid4(),
            "source_type": "user",
            "model_version": None,
            "created_by": "integration_test",
            "raw_input": text,
        },
    )
