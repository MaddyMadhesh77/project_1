from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import TrustEvent
from app.services import retrieval, trust_engine, versioning
from app.services.embedding import get_embedding_service
from app.services.extractor import RuleBasedExtractor, format_candidate_text
from app.services.features import compute_features
from app.services.llm_client import get_llm_client

router = APIRouter(tags=["chat"])

_extractor = RuleBasedExtractor()


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str
    history: list[ChatMessageIn] = []


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

    # Phase 2 pipeline (DESIGN.md 6.3-6.6): extraction -> embed -> hybrid
    # retrieval -> feature engineering -> trust engine -> versioning. Every
    # candidate is still *stored* (as a new version) regardless of decision --
    # store/review/reject only changes the trust_score/decision/status
    # attached to it, never whether it's written at all. Flushing inside
    # versioning.write_version means a second candidate extracted from the
    # same message can see the first one via retrieval.
    for candidate in _extractor.extract(body.message):
        text = format_candidate_text(candidate)
        embedding = embedding_service.embed(text)

        hits = await retrieval.hybrid_search(db, embedding=embedding, text=text, top_k=settings.retrieval_top_k)
        best_match = (
            hits[0] if hits and hits[0].similarity >= settings.retrieval_same_memory_threshold else None
        )

        feature_vector = await compute_features(
            db, candidate=candidate, best_match=best_match, source_type="user", llm_client=llm_client
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
                details=trust_result.breakdown,
            )
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

    await db.commit()

    return ChatResponse(conversation_id=conversation_id, reply=reply, stored_memories=stored)
