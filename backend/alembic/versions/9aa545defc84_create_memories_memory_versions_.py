"""create memories memory_versions provenance

Revision ID: 9aa545defc84
Revises:
Create Date: 2026-07-28 12:39:46.041399

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = '9aa545defc84'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memories",
        sa.Column("memory_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # current_version_id's FK to memory_versions is added below, after
        # memory_versions exists (the two tables reference each other).
        sa.Column("current_version_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="trusted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "memory_versions",
        sa.Column("version_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("memory_id", UUID(as_uuid=True), sa.ForeignKey("memories.memory_id"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("trust_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("trust_breakdown", JSONB, nullable=False),
        sa.Column("decision", sa.String, nullable=False),
        sa.Column("content_hash", sa.String, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("memory_id", "version_number", name="uq_memory_versions_memory_id_version_number"),
    )

    op.create_foreign_key(
        "fk_memories_current_version_id",
        "memories",
        "memory_versions",
        ["current_version_id"],
        ["version_id"],
    )

    op.create_table(
        "provenance",
        sa.Column("version_id", UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), primary_key=True),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String, nullable=False),
        sa.Column("model_version", sa.String, nullable=True),
        sa.Column("created_by", sa.String, nullable=True),
        sa.Column("raw_input", sa.Text, nullable=True),
    )

    op.execute(
        "CREATE INDEX ix_memory_versions_embedding ON memory_versions "
        "USING ivfflat (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_memory_versions_text_fts ON memory_versions "
        "USING gin (to_tsvector('english', text))"
    )


def downgrade() -> None:
    op.drop_table("provenance")
    op.drop_constraint("fk_memories_current_version_id", "memories", type_="foreignkey")
    op.drop_table("memory_versions")
    op.drop_table("memories")
