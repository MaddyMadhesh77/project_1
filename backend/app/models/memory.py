import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Memory(Base):
    __tablename__ = "memories"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    # FK added via ALTER TABLE in the migration (memory_versions references
    # memories, so this side of the cycle can't be declared inline).
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("memory_versions.version_id", use_alter=True, name="fk_memories_current_version_id"),
        nullable=True,
    )
    # trusted | low_trust | quarantined | rolled_back -- see
    # versioning.STATUS_BY_DECISION (a "reject" decision lands as quarantined)
    # and rollback (removed -> rolled_back).
    status: Mapped[str] = mapped_column(sa.String, nullable=False, server_default="trusted")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
