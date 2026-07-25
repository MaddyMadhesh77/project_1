"""add trust_events table

Revision ID: 66a90e4e5de5
Revises: 9aa545defc84
Create Date: 2026-07-28 12:57:58.505299

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '66a90e4e5de5'
down_revision: Union[str, None] = '9aa545defc84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trust_events",
        sa.Column("event_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("version_id", UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), nullable=False),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("trust_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_trust_events_version_id", "trust_events", ["version_id"])


def downgrade() -> None:
    op.drop_index("ix_trust_events_version_id", table_name="trust_events")
    op.drop_table("trust_events")
