import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DependencyEdge(Base):
    __tablename__ = "dependency_edges"
    __table_args__ = (
        sa.UniqueConstraint("parent_version_id", "child_version_id", name="uq_dependency_edges_parent_child"),
    )

    edge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    parent_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), nullable=False
    )
    child_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), nullable=False
    )
    # derived_from is the only relation type minted today (DESIGN.md 6.9); the
    # column exists so future relation kinds don't require a migration.
    relation_type: Mapped[str] = mapped_column(sa.String, nullable=False, server_default="derived_from")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
