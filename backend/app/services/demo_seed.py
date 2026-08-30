from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Provenance, TrustEvent
from app.services import graph, merkle, trust_engine, versioning
from app.services.embedding import get_embedding_service
from app.services.features import FeatureVector

# DESIGN.md §9 flow-2 demo chain: "likes Python" -> "recommend Django" ->
# "recommend FastAPI", each memory derived from the one before it via a
# dependency_edges row (DESIGN.md 6.9). Bypasses the chat pipeline's regex
# extractor -- which has no "recommend X" predicate category (DESIGN.md
# 6.1) -- and writes versions/edges directly through the same services the
# pipeline uses.
#
# Shared by scripts/seed_demo.py (the CLI entry point) and
# app/api/routes/admin.py's POST /admin/reset (bugs.md #11), so both stay in
# sync with a single source of truth for what "a freshly seeded demo" means.

SEED_CONVERSATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000042")

SOURCE_RELIABILITY = {"user": 1.0, "llm_inference": 0.6}

# (stored text, provenance source_type, raw utterance/reply it came from).
# Each node uses a different predicate category (DESIGN.md 6.1) so retrieval
# doesn't treat them as updates to the same memory -- the chain's derivation
# structure comes entirely from the explicit dependency edges below.
CHAIN = [
    ("preference: Python", "user", "I like Python"),
    ("goal: learn Django", "llm_inference", "Since you like Python, consider learning Django."),
    ("goal: learn FastAPI", "llm_inference", "Since you're learning Django, FastAPI is a natural next step."),
]


async def already_seeded(db: AsyncSession) -> bool:
    result = await db.execute(
        sa.select(sa.func.count()).select_from(Provenance).where(Provenance.conversation_id == SEED_CONVERSATION_ID)
    )
    return result.scalar_one() > 0


async def seed_demo(db: AsyncSession, settings: Settings) -> list[str] | None:
    """Writes the demo chain. Returns None if already seeded (a fixed
    conversation_id makes this check cheap and exact); otherwise one
    description line per memory written. Does not commit -- callers control
    the transaction (scripts/seed_demo.py commits once at the end;
    POST /admin/reset commits as part of its own truncate+reseed flow).
    """
    if await already_seeded(db):
        return None

    embedding_service = get_embedding_service()
    lines: list[str] = []
    prior_version_id: uuid.UUID | None = None
    for text, source_type, raw_input in CHAIN:
        embedding = embedding_service.embed(text)

        features = FeatureVector(
            similarity=0.0,
            contradiction=0.0,
            source_reliability=SOURCE_RELIABILITY[source_type],
            memory_age_days=0.0,
            prior_trust_score=0.0,
            corroboration_count=0,
            conversation_recency=1.0,
            has_match=False,
        )
        trust_result = trust_engine.score_candidate(features, settings)

        version = await versioning.write_version(
            db,
            memory_id=None,
            text=text,
            embedding=embedding,
            trust_score=trust_result.score,
            trust_breakdown=trust_result.breakdown,
            decision=trust_result.decision,
            provenance_fields={
                "conversation_id": SEED_CONVERSATION_ID,
                "source_type": source_type,
                "model_version": None,
                "created_by": "seed_demo",
                "raw_input": raw_input,
            },
        )

        # bugs.md Bug D: without this, a fresh seed left /logs empty and
        # /analytics/summary's trend flat -- chat.py writes one of these per
        # candidate (DESIGN.md 5: trust_events "feeds ML training"), and this
        # is the only other place that mints memory versions, so it needs the
        # same bookkeeping to keep the Phase 8 pages demoable right after a
        # reset/seed.
        db.add(
            TrustEvent(
                version_id=version.version_id,
                event_type="created",
                trust_score=trust_result.score,
                details={"breakdown": trust_result.breakdown, "features": vars(features)},
            )
        )

        if prior_version_id is not None:
            await graph.record_edge(db, parent_version_id=prior_version_id, child_version_id=version.version_id)

        prior_version_id = version.version_id
        lines.append(
            f"seeded {text!r} -> memory {version.memory_id} version {version.version_id} (trust {trust_result.score})"
        )

    # Same reason chat.py recomputes once after its whole candidate loop
    # (services/versioning.py no longer does this per-write): without it,
    # merkle_roots stays empty after a seed/reset and /admin/integrity has no
    # root to show or verify against.
    await merkle.compute_and_store_root(db)

    return lines
