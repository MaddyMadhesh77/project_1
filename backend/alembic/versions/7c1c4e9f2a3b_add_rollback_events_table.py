"""add rollback_events table

Revision ID: 7c1c4e9f2a3b
Revises: 3aee8df60746
Create Date: 2026-07-28 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = '7c1c4e9f2a3b'
down_revision: Union[str, None] = '3aee8df60746'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rollback_events",
        sa.Column("rollback_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("root_version_id", UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), nullable=False),
        sa.Column("affected_version_ids", JSONB, nullable=False),
        sa.Column("triggered_by", sa.String, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_rollback_events_root_version_id", "rollback_events", ["root_version_id"])


def downgrade() -> None:
    op.drop_index("ix_rollback_events_root_version_id", table_name="rollback_events")
    op.drop_table("rollback_events")
