import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

EMBEDDING_DIM = 384


class MemoryVersion(Base):
    __tablename__ = "memory_versions"
    __table_args__ = (sa.UniqueConstraint("memory_id", "version_number", name="uq_memory_versions_memory_id_version_number"),)

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("memories.memory_id"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    trust_score: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2), nullable=False)
    trust_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # store | review | reject
    decision: Mapped[str] = mapped_column(sa.String, nullable=False)
    content_hash: Mapped[str] = mapped_column(sa.String, nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
