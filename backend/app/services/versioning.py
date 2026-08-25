from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory, MemoryVersion, Provenance
from app.services import graph
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
        prior_version_id = None
    else:
        # SELECT ... FOR UPDATE: serializes concurrent writers targeting the
        # same memory_id so the max(version_number)+1 read below can't race.
        # Without the row lock, two concurrent updates to the same memory
        # both read the same max and try to insert the same version_number,
        # tripping the unique constraint and surfacing as a 500.
        memory = (
            await db.execute(sa.select(Memory).where(Memory.memory_id == memory_id).with_for_update())
        ).scalar_one_or_none()
        if memory is None:
            raise ValueError(f"memory {memory_id} not found")
        prior_version_id = memory.current_version_id
        if prior_version_id is not None:
            prior = await db.get(MemoryVersion, prior_version_id)
            if prior is not None:
                prior.is_active = False
        max_version_number = (
            await db.execute(
                sa.select(sa.func.max(MemoryVersion.version_number)).where(MemoryVersion.memory_id == memory_id)
            )
        ).scalar_one()
        version_number = (max_version_number or 0) + 1

    version = MemoryVersion(
        memory_id=memory.memory_id,
        version_number=version_number,
        text=text,
        embedding=embedding,
        trust_score=trust_score,
        trust_breakdown=trust_breakdown,
        decision=decision,
        content_hash="pending",  # overwritten below once we know the as-stored embedding
        is_active=True,
    )
    db.add(version)
    await db.flush()

    # content_hash must be derived from the embedding as Postgres actually
    # persists/returns it, not the in-memory value passed in above: pgvector's
    # `vector` column does not round-trip float components bit-exactly (found
    # empirically -- ~1e-9 absolute noise per component, comfortably inside
    # float32 precision but enough to flip a fixed-precision-formatted digit
    # on roughly 1 in a few hundred writes given 384 components). Hashing the
    # pre-flush value here would make Phase 5's verify_integrity mismatch on
    # legitimate, untouched rows the first time they're read back. Refreshing
    # from the DB before hashing makes write-time and verify-time hash the
    # same bits by construction, instead of a decimal-precision race.
    await db.refresh(version, attribute_names=["embedding"])
    version.content_hash = compute_content_hash(text, list(version.embedding), provenance_fields)

    memory.current_version_id = version.version_id
    memory.status = STATUS_BY_DECISION[decision]
    memory.updated_at = datetime.now(timezone.utc)

    db.add(Provenance(version_id=version.version_id, **provenance_fields))

    if prior_version_id is not None:
        await graph.carry_forward_edges(db, old_version_id=prior_version_id, new_version_id=version.version_id)

    # Merkle tree (DESIGN.md 6.8): recomputing the root is deliberately NOT
    # done here. It's O(N) in the total number of active leaves, so a route
    # writing several versions in one transaction (chat.py's multi-candidate
    # loop, rollback.py's dependency-chain recovery) used to pay a full tree
    # rebuild per version instead of one per transaction. Callers recompute
    # once, after all of a request's writes, via services/merkle.
    # compute_and_store_root -- see chat.py, attack.py, rollback.py.

    return version
