import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RollbackOutcome(Base):
    """One row per node (poisoned root + every affected descendant) a
    rollback run touched -- replaces rollback_events.affected_version_ids
    (a JSONB array) so "which rollbacks affected memory X" is an indexed
    query instead of a full-table JSON scan.
    """

    __tablename__ = "rollback_outcomes"

    outcome_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    rollback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("rollback_events.rollback_id"), nullable=False, index=True
    )
    # Position within this rollback's processing_order (poisoned root = 0),
    # so GET /rollback/{id} can ORDER BY this and reproduce the same
    # root-first ordering the POST response returns directly from memory --
    # the frontend's staged-reveal animation (Rollback.tsx) depends on it.
    outcome_index: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    memory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("memories.memory_id"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), nullable=False
    )
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # kept | reverted | removed
    outcome: Mapped[str] = mapped_column(sa.String, nullable=False)
    new_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), nullable=False
    )
    trust_score: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2), nullable=False)
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
