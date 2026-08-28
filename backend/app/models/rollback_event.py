import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RollbackEvent(Base):
    __tablename__ = "rollback_events"

    rollback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    root_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), nullable=False
    )
    # Per-node results live in rollback_outcomes (one row per affected
    # version, FK'd to rollback_id/memory_id/version_id) rather than here as
    # a JSONB blob -- see app/models/rollback_outcome.py. A JSONB array of
    # {version_id, memory_id, ...} objects couldn't be queried by memory_id
    # ("which rollbacks affected memory X") without a full-table JSON scan.
    triggered_by: Mapped[str] = mapped_column(sa.String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    # Merkle root as of the moment this rollback finished writing, so
    # GET /rollback/{id} can re-display the root that was actually true at
    # that time instead of whatever the store's *current* root happens to be.
    merkle_root_hash: Mapped[str | None] = mapped_column(sa.String, nullable=True)
