from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory, MemoryVersion, Provenance
from app.services.hashing import compute_content_hash

# memories.status is a denormalized rollup of the current version's decision
# (DESIGN.md 5 notes). "quarantined" for reject rather than "rejected" --
# matches the flow-1 pitch script's dashboard wording (DESIGN.md 9).
STATUS_BY_DECISION = {"store": "trusted", "review": "low_trust", "reject": "quarantined"}


async def write_version(
    db: AsyncSession,
    *,
    memory_id: uuid.UUID | None,
    text: str,
    embedding: list[float],
    trust_score: float,
    trust_breakdown: dict,
    decision: str,
    provenance_fields: dict,
) -> MemoryVersion:
    """Insert a new memory version -- rows are never mutated (DESIGN.md 6.6).

    If `memory_id` is None this is a brand-new memory (version 1). Otherwise
    it's an update to an existing one: the prior current version is flipped
    inactive and `memories.current_version_id` advances to the new version
    *regardless of decision*. A low-trust/rejected update still becomes the
    store's current belief (flagged via `status`, not hidden) -- this is what
    makes Phase 6's "revert current_version_id to the prior version" rollback
    step meaningful (DESIGN.md 6.10 step 3): there has to be something to
    revert *from*.
    """
    if memory_id is None:
        memory = Memory(status=STATUS_BY_DECISION[decision])
        db.add(memory)
        await db.flush()
        version_number = 1
    else:
        memory = await db.get(Memory, memory_id)
        if memory is None:
            raise ValueError(f"memory {memory_id} not found")
        if memory.current_version_id is not None:
            prior = await db.get(MemoryVersion, memory.current_version_id)
            if prior is not None:
                prior.is_active = False
        max_version_number = (
            await db.execute(
                sa.select(sa.func.max(MemoryVersion.version_number)).where(MemoryVersion.memory_id == memory_id)
            )
        ).scalar_one()
        version_number = (max_version_number or 0) + 1

    content_hash = compute_content_hash(text, embedding, provenance_fields)

    version = MemoryVersion(
        memory_id=memory.memory_id,
        version_number=version_number,
        text=text,
        embedding=embedding,
        trust_score=trust_score,
        trust_breakdown=trust_breakdown,
        decision=decision,
        content_hash=content_hash,
        is_active=True,
    )
    db.add(version)
    await db.flush()

    memory.current_version_id = version.version_id
    memory.status = STATUS_BY_DECISION[decision]
    memory.updated_at = datetime.now(timezone.utc)

    db.add(Provenance(version_id=version.version_id, **provenance_fields))

    return version
