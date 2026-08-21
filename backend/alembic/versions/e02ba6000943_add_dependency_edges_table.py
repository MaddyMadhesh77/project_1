"""add dependency_edges table

Revision ID: e02ba6000943
Revises: 66a90e4e5de5
Create Date: 2026-07-28 14:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'e02ba6000943'
down_revision: Union[str, None] = '66a90e4e5de5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dependency_edges",
        sa.Column("edge_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_version_id", UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), nullable=False),
        sa.Column("child_version_id", UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), nullable=False),
        sa.Column("relation_type", sa.String, nullable=False, server_default="derived_from"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("parent_version_id", "child_version_id", name="uq_dependency_edges_parent_child"),
    )
    op.create_index("ix_dependency_edges_parent_version_id", "dependency_edges", ["parent_version_id"])
    op.create_index("ix_dependency_edges_child_version_id", "dependency_edges", ["child_version_id"])


def downgrade() -> None:
    op.drop_index("ix_dependency_edges_child_version_id", table_name="dependency_edges")
    op.drop_index("ix_dependency_edges_parent_version_id", table_name="dependency_edges")
    op.drop_table("dependency_edges")
