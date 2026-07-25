from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory, MemoryVersion
from app.services.extractor import CandidateMemory, format_candidate_text, parse_stored_text
from app.services.llm_client import LLMClient
from app.services.retrieval import RetrievalHit

# Weight by source type (DESIGN.md 6.4 "source_reliability"): user statement >
# admin override > LLM inference > uncorroborated system inference.
SOURCE_RELIABILITY = {
    "user": 1.0,
    "admin_override": 1.0,
    "llm_inference": 0.6,
    "system": 0.4,
}


@dataclass
class FeatureVector:
    similarity: float  # cosine similarity to best-matching existing memory (0 if none)
    contradiction: float  # 0 (consistent) .. 1 (direct contradiction)
    source_reliability: float
    memory_age_days: float
    prior_trust_score: float
    corroboration_count: int
    conversation_recency: float
    has_match: bool  # whether an existing memory was matched at all


async def _count_corroborating(
    db: AsyncSession, *, predicate: str, value: str, polarity: int, exclude_memory_id: uuid.UUID
) -> int:
    """How many *other* active memories independently assert the same
    (predicate, value, polarity) -- DESIGN.md 6.4 "corroboration_count"."""
    expected_text = format_candidate_text(CandidateMemory(predicate=predicate, value=value, raw_text="", polarity=polarity))
    result = await db.execute(
        sa.select(sa.func.count(MemoryVersion.version_id))
        .join(Memory, Memory.current_version_id == MemoryVersion.version_id)
        .where(MemoryVersion.is_active.is_(True))
        .where(MemoryVersion.memory_id != exclude_memory_id)
        .where(sa.func.lower(MemoryVersion.text) == expected_text.lower())
    )
    return result.scalar_one()


async def compute_features(
    db: AsyncSession,
    *,
    candidate: CandidateMemory,
    best_match: RetrievalHit | None,
    source_type: str,
    llm_client: LLMClient,
) -> FeatureVector:
    source_reliability = SOURCE_RELIABILITY.get(source_type, 0.5)
    # MVP simplification: every chat turn is part of the live, active
    # conversation -- there's no notion of a "stale" background conversation
    # in this single-session demo, so this feature is a flat 1.0 for now.
    conversation_recency = 1.0

    if best_match is None:
        return FeatureVector(
            similarity=0.0,
            contradiction=0.0,
            source_reliability=source_reliability,
            memory_age_days=0.0,
            prior_trust_score=0.0,
            corroboration_count=0,
            conversation_recency=conversation_recency,
            has_match=False,
        )

    match_predicate, match_value, match_polarity = parse_stored_text(best_match.text)
    candidate_text = format_candidate_text(candidate)

    if match_predicate != candidate.predicate:
        # Different predicate categories matched by retrieval -- ambiguous,
        # fall back to the LLM judge (DESIGN.md 6.4).
        contradiction = await llm_client.judge_contradiction(candidate_text, best_match.text)
    elif candidate.value.strip().lower() == match_value.strip().lower():
        # Same predicate + same value: an exact polarity flip is a hard
        # contradiction ("like Python" vs "hate Python"); matching polarity
        # is corroboration.
        contradiction = 1.0 if match_polarity != candidate.polarity else 0.0
    else:
        # Same predicate, different value (e.g. a location change) -- could be
        # a legitimate correction or a poisoning attempt; ambiguous either way.
        contradiction = await llm_client.judge_contradiction(candidate_text, best_match.text)

    memory = await db.get(Memory, best_match.memory_id)
    age_days = (datetime.now(timezone.utc) - memory.created_at).days if memory else 0.0

    corroboration_count = await _count_corroborating(
        db,
        predicate=candidate.predicate,
        value=candidate.value,
        polarity=candidate.polarity,
        exclude_memory_id=best_match.memory_id,
    )

    return FeatureVector(
        similarity=best_match.similarity,
        contradiction=contradiction,
        source_reliability=source_reliability,
        memory_age_days=float(age_days),
        prior_trust_score=best_match.trust_score,
        corroboration_count=corroboration_count,
        conversation_recency=conversation_recency,
        has_match=True,
    )
