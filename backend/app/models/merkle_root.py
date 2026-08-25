import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MerkleRoot(Base):
    __tablename__ = "merkle_roots"

    root_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    root_hash: Mapped[str] = mapped_column(sa.String, nullable=False)
    leaf_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
    # True insertion order -- `computed_at` is transaction time (identical for
    # every row written within one multi-write transaction, e.g. a rollback),
    # so it can't disambiguate "latest" on its own. See migration
    # 8b2e5f6a1c9d for the false-tamper bug this fixes.
    sequence_number: Mapped[int] = mapped_column(
        sa.BigInteger, server_default=sa.text("nextval('merkle_roots_sequence_number_seq')"), nullable=False
    )
