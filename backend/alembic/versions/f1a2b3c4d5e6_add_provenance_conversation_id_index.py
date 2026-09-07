"""add index on provenance.conversation_id

Revision ID: f1a2b3c4d5e6
Revises: d4e9a1f2b8c3
Create Date: 2026-08-21 00:05:00.000000

"Show all memories from conversation X" is a natural admin/debug query
(conversation_id is already stored on every provenance row) with no index
to support it -- forces a full table scan of provenance as the table grows.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'd4e9a1f2b8c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_provenance_conversation_id", "provenance", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_provenance_conversation_id", table_name="provenance")
