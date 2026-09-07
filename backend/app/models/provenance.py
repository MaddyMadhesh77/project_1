import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Provenance(Base):
    __tablename__ = "provenance"

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), primary_key=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # user | llm_inference | admin_override | system
    source_type: Mapped[str] = mapped_column(sa.String, nullable=False)
    model_version: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    created_by: Mapped[str | None] = mapped_column(sa.String, nullable=True)
    raw_input: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
