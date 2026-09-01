"""add rollback_events.merkle_root_hash -- fix GET /rollback/{id} showing the wrong root

Revision ID: c3d8f4a1b6e7
Revises: 8b2e5f6a1c9d
Create Date: 2026-08-19 00:00:00.000000

GET /rollback/{rollback_id} used to return `merkle.latest_root()` -- the
store's CURRENT root -- instead of the root that was true when that rollback
actually ran. Any write after the rollback (including a later, unrelated
rollback) silently changes what a historical rollback appears to have
produced, which is actively misleading in a security/audit context. Persist
the root at write time instead of re-deriving it later from mutable state.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d8f4a1b6e7'
down_revision: Union[str, None] = '8b2e5f6a1c9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rollback_events", sa.Column("merkle_root_hash", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("rollback_events", "merkle_root_hash")
