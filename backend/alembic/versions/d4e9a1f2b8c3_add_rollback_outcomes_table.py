"""replace rollback_events.affected_version_ids JSONB with rollback_outcomes table

Revision ID: d4e9a1f2b8c3
Revises: c3d8f4a1b6e7
Create Date: 2026-08-21 00:00:00.000000

rollback_events.affected_version_ids was a JSONB array of
{version_id, memory_id, text, outcome, new_version_id, trust_score, reason}
objects. "Which rollbacks affected memory X" -- a natural question for an
admin investigating a memory's history -- had no index to answer it without
a full-table JSON scan. rollback_outcomes gives each affected node its own
row with real FK columns (rollback_id, memory_id, version_id), indexed.

Backfills existing rollback_events rows from their JSONB payload before
dropping the column, so no history is lost.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = 'd4e9a1f2b8c3'
down_revision: Union[str, None] = 'c3d8f4a1b6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rollback_outcomes",
        sa.Column("outcome_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("rollback_id", UUID(as_uuid=True), sa.ForeignKey("rollback_events.rollback_id"), nullable=False),
        sa.Column("outcome_index", sa.Integer(), nullable=False),
        sa.Column("memory_id", UUID(as_uuid=True), sa.ForeignKey("memories.memory_id"), nullable=False),
        sa.Column("version_id", UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("new_version_id", UUID(as_uuid=True), sa.ForeignKey("memory_versions.version_id"), nullable=False),
        sa.Column("trust_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_index("ix_rollback_outcomes_rollback_id", "rollback_outcomes", ["rollback_id"])
    op.create_index("ix_rollback_outcomes_memory_id", "rollback_outcomes", ["memory_id"])

    # Backfill from the JSONB column before dropping it. WITH ORDINALITY
    # preserves the original array position as outcome_index (0-based, so
    # subtract 1) -- keeps this in the DB rather than round-tripping through
    # Python.
    op.execute(
        """
        INSERT INTO rollback_outcomes
            (rollback_id, outcome_index, memory_id, version_id, text, outcome, new_version_id, trust_score, reason)
        SELECT
            re.rollback_id,
            (ord - 1)::integer,
            (elem->>'memory_id')::uuid,
            (elem->>'version_id')::uuid,
            elem->>'text',
            elem->>'outcome',
            (elem->>'new_version_id')::uuid,
            (elem->>'trust_score')::numeric,
            elem->>'reason'
        FROM rollback_events re,
             jsonb_array_elements(re.affected_version_ids) WITH ORDINALITY AS t(elem, ord)
        WHERE jsonb_typeof(re.affected_version_ids) = 'array'
        """
    )

    op.drop_column("rollback_events", "affected_version_ids")


def downgrade() -> None:
    op.add_column("rollback_events", sa.Column("affected_version_ids", JSONB(), nullable=True))
    op.execute(
        """
        UPDATE rollback_events re
        SET affected_version_ids = sub.payload
        FROM (
            SELECT
                rollback_id,
                jsonb_agg(jsonb_build_object(
                    'version_id', version_id,
                    'memory_id', memory_id,
                    'text', text,
                    'outcome', outcome,
                    'new_version_id', new_version_id,
                    'trust_score', trust_score,
                    'reason', reason
                ) ORDER BY outcome_index) AS payload
            FROM rollback_outcomes
            GROUP BY rollback_id
        ) sub
        WHERE re.rollback_id = sub.rollback_id
        """
    )
    op.execute("UPDATE rollback_events SET affected_version_ids = '[]'::jsonb WHERE affected_version_ids IS NULL")
    op.alter_column("rollback_events", "affected_version_ids", nullable=False)

    op.drop_index("ix_rollback_outcomes_memory_id", table_name="rollback_outcomes")
    op.drop_index("ix_rollback_outcomes_rollback_id", table_name="rollback_outcomes")
    op.drop_table("rollback_outcomes")
