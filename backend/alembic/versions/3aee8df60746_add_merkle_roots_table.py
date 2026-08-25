"""add merkle_roots table

Revision ID: 3aee8df60746
Revises: e02ba6000943
Create Date: 2026-07-28 14:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '3aee8df60746'
down_revision: Union[str, None] = 'e02ba6000943'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "merkle_roots",
        sa.Column("root_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("root_hash", sa.String, nullable=False),
        sa.Column("leaf_count", sa.Integer, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_merkle_roots_computed_at", "merkle_roots", ["computed_at"])


def downgrade() -> None:
    op.drop_index("ix_merkle_roots_computed_at", table_name="merkle_roots")
    op.drop_table("merkle_roots")
