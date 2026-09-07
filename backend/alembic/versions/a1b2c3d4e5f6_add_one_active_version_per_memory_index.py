"""add partial unique index enforcing one active version per memory

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-08-21 00:00:00.000000

bugs.md Bug B: nothing at the DB level stopped memory_versions.is_active
from being true on more than one row for the same memory_id, which would
leave memories.current_version_id and /memories/{id}/history disagreeing on
what "current" means. services/versioning.py's SELECT ... FOR UPDATE already
serializes concurrent writers per memory_id in application code, so this
index is defense-in-depth rather than the primary fix -- it turns any future
code path that flips is_active without going through write_version's locked
section into an immediate constraint violation instead of silent duplicate
"current" rows.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_memory_versions_one_active_per_memory",
        "memory_versions",
        ["memory_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_memory_versions_one_active_per_memory", table_name="memory_versions")
