from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import TrustEvent
from app.services import graph, merkle, retrieval, trust_engine, versioning
from app.services.embedding import get_embedding_service
from app.services.extractor import RuleBasedExtractor, format_candidate_text
from app.services.features import compute_features
from app.services.llm_client import get_llm_client

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)

_extractor = RuleBasedExtractor()


class ChatMessageIn(BaseModel):
    # The Anthropic API only accepts "user"/"assistant" in a messages list --
    # "system" or a typo passed straight through role: str used to surface as
    # a cryptic upstream API error instead of a clean 422 at the request
    # boundary.
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    # Unbounded input would be embedded, LLM-called, and Merkle-hashed at
    # whatever size the client sends -- cap it well above any real chat
    # message so a megabyte-sized payload can't reach the pipeline at all.
    message: str = Field(max_length=4000)
    history: list[ChatMessageIn] = Field(default_factory=list, max_length=50)


class StoredMemoryOut(BaseModel):
    memory_id: uuid.UUID
    version_id: uuid.UUID
    text: str
    trust_score: float
    decision: str


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    reply: str
    stored_memories: list[StoredMemoryOut]
    failed_candidates: int = 0


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    conversation_id = body.conversation_id or uuid.uuid4()

    llm_client = get_llm_client(settings)
    history = [turn.model_dump() for turn in body.history]
    reply = await llm_client.reply(body.message, history)

    embedding_service = get_embedding_service()
    stored: list[StoredMemoryOut] = []
    failed_candidates = 0

    # Phase 2 pipeline (DESIGN.md 6.3-6.6): extraction -> embed -> hybrid
    # retrieval -> feature engineering -> trust engine -> versioning. Every
    # candidate is still *stored* (as a new version) regardless of decision --
    # store/review/reject only changes the trust_score/decision/status
    # attached to it, never whether it's written at all. Flushing inside
    # versioning.write_version means a second candidate extracted from the
    # same message can see the first one via retrieval.
    #
    # Each candidate gets its own SAVEPOINT: all candidates from one message
    # otherwise shared the single outer transaction, so a failure partway
    # through candidate 2 would silently roll back candidate 1's already-
    # succeeded writes -- while `stored` (built up in memory) still listed
    # candidate 1 as stored in the response. Isolating per candidate means a
    # later failure can only roll back that candidate's own work.
    for candidate in _extractor.extract(body.message):
        try:
            async with db.begin_nested():
                text = format_candidate_text(candidate)
                embedding = embedding_service.embed(text)

                hits = await retrieval.hybrid_search(
                    db, embedding=embedding, text=text, top_k=settings.retrieval_top_k
                )
                best_match = (
                    hits[0] if hits and hits[0].similarity >= settings.retrieval_same_memory_threshold else None
                )

                feature_vector = await compute_features(
                    db,
                    candidate=candidate,
                    best_match=best_match,
                    source_type="user",
                    llm_client=llm_client,
                    conversation_id=conversation_id,
                    settings=settings,
                )
                trust_result = trust_engine.score_candidate(feature_vector, settings)

                provenance_fields = {
                    "conversation_id": conversation_id,
                    "source_type": "user",
                    "model_version": None,
                    "created_by": "user",
                    "raw_input": candidate.raw_text,
                }

                version = await versioning.write_version(
                    db,
                    memory_id=best_match.memory_id if best_match else None,
                    text=text,
                    embedding=embedding,
                    trust_score=trust_result.score,
                    trust_breakdown=trust_result.breakdown,
                    decision=trust_result.decision,
                    provenance_fields=provenance_fields,
                )

                db.add(
                    TrustEvent(
                        version_id=version.version_id,
                        event_type="created" if best_match is None else "updated",
                        trust_score=trust_result.score,
                        # "features" (the raw FeatureVector, not just the breakdown)
                        # is what app/ml/train.py needs to retrain on real outcomes
                        # (DESIGN.md 5: trust_events "feeds ML training") -- a
                        # rollback's later kept/reverted/removed verdict on this same
                        # version_id supplies the label (see services/rollback.py).
                        details={"breakdown": trust_result.breakdown, "features": vars(feature_vector)},
                    )
                )

                # Dependency graph (DESIGN.md 6.9): only when this candidate became a
                # brand-new memory (best_match is None -- an update to an *existing*
                # memory isn't "derived from" itself, it's the same memory versioned).
                # Retrieval hits that were related but not similar enough to count as
                # the same memory are what Feature Engineering also treats as
                # "supporting context" for this candidate -- record a derivation edge
                # from each.
                if best_match is None:
                    for hit in hits:
                        if hit.similarity >= settings.dependency_edge_similarity_threshold:
                            await graph.record_edge(
                                db, parent_version_id=hit.version_id, child_version_id=version.version_id
                            )

                stored.append(
                    StoredMemoryOut(
                        memory_id=version.memory_id,
                        version_id=version.version_id,
                        text=text,
                        trust_score=trust_result.score,
                        decision=trust_result.decision,
                    )
                )
        except Exception:
            failed_candidates += 1
            logger.exception("failed to store candidate %r for conversation %s", candidate.raw_text, conversation_id)

    if stored:
        # Recompute the Merkle root once for this whole message, not once per
        # candidate (versioning.write_version no longer does this itself) --
        # an O(N)-in-total-leaves tree rebuild per candidate made a
        # multi-candidate message pay for several full rebuilds in one
        # transaction. Skipped entirely when nothing was actually stored
        # (the common case: most chat turns extract zero candidates).
        await merkle.compute_and_store_root(db)

    await db.commit()

    return ChatResponse(
        conversation_id=conversation_id, reply=reply, stored_memories=stored, failed_candidates=failed_candidates
    )
