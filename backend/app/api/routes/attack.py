from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import MemoryVersion
from app.services import merkle, versioning
from app.services.embedding import get_embedding_service

router = APIRouter(tags=["attack"])


class TamperRequest(BaseModel):
    version_id: uuid.UUID
    text: str | None = Field(default=None, max_length=4000)  # if omitted, appends a tamper marker to the current text


class TamperResponse(BaseModel):
    version_id: uuid.UUID
    old_text: str
    new_text: str


@router.post("/attack/tamper-db", response_model=TamperResponse)
async def tamper_db(body: TamperRequest, db: AsyncSession = Depends(get_db)) -> TamperResponse:
    """Demo-only (DESIGN.md 9 flow 3): directly UPDATEs memory_versions.text
    via raw SQL, bypassing the API/pipeline entirely -- simulates a rogue DBA
    editing a row in place. Deliberately does NOT touch content_hash, so
    POST /integrity/verify's row-level recompute-and-compare is what catches
    it, exactly like a real out-of-band tamper would leave the pre-tamper
    hash stranded in place.
    """
    version = await db.get(MemoryVersion, body.version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="version not found")

    old_text = version.text
    new_text = body.text if body.text is not None else f"{old_text} [TAMPERED]"

    await db.execute(
        text("UPDATE memory_versions SET text = :new_text WHERE version_id = :version_id"),
        {"new_text": new_text, "version_id": body.version_id},
    )
    await db.commit()

    return TamperResponse(version_id=body.version_id, old_text=old_text, new_text=new_text)


class InjectPoisonRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)  # canonical stored text, e.g. "preference: not Python"
    memory_id: uuid.UUID | None = None  # None => brand-new memory; otherwise versions an existing one
    # Same 0-100 scale as every trust score; out-of-range values used to be
    # stored as-is (negative scores) or overflow the column (a 500).
    forced_trust_score: float = Field(95.0, ge=0, le=100)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class InjectPoisonResponse(BaseModel):
    memory_id: uuid.UUID
    version_id: uuid.UUID
    text: str
    trust_score: float
    decision: str


@router.post("/attack/inject-poison", response_model=InjectPoisonResponse)
async def inject_poison(body: InjectPoisonRequest, db: AsyncSession = Depends(get_db)) -> InjectPoisonResponse:
    """Demo-only (DESIGN.md 6/9): force-writes a memory version through the
    real versioning/hashing/Merkle pipeline while completely bypassing
    retrieval, feature engineering, and the trust engine -- simulating an
    attacker whose fabricated memory got past the front-line gate and now
    sits in the store looking exactly as legitimate as anything else
    (`decision=store`, a high `forced_trust_score`). This is what the
    Rollback Engine's "recover even when the gate missed it" story needs a
    reliably-reproducible trigger for -- unlike POST /attack/tamper-db (which
    bypasses the API/pipeline via raw SQL), this goes through the normal
    write path so the injected memory has a real content_hash, participates
    in the Merkle tree, and can anchor dependency edges, exactly like a
    genuinely-admitted memory would.
    """
    embedding = await get_embedding_service().aembed(body.text)

    # versioning.write_version already looks up (and locks) the memory row
    # by id and raises ValueError if it doesn't exist -- a separate existence
    # fetch here just to check for None was a wasted round trip whose result
    # was otherwise discarded.
    try:
        version = await versioning.write_version(
            db,
            memory_id=body.memory_id,
            text=body.text,
            embedding=embedding,
            trust_score=body.forced_trust_score,
            trust_breakdown={"injected_by_attack_simulator": body.forced_trust_score},
            decision="store",
            provenance_fields={
                "conversation_id": uuid.uuid4(),
                "source_type": "user",
                "model_version": None,
                "created_by": "attack_simulator",
                "raw_input": f"[attack simulator] {body.text}",
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # write_version no longer recomputes the Merkle root itself -- see
    # services/versioning.py -- so the single write here needs one explicit
    # recompute before commit.
    await merkle.compute_and_store_root(db)
    await db.commit()

    return InjectPoisonResponse(
        memory_id=version.memory_id,
        version_id=version.version_id,
        text=body.text,
        trust_score=body.forced_trust_score,
        decision="store",
    )
