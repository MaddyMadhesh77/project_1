"""add merkle_roots.sequence_number -- fix false-tamper on multi-write transactions

Revision ID: 8b2e5f6a1c9d
Revises: 4f1a9b3c7d2e
Create Date: 2026-07-28 20:30:00.000000

`merkle_roots.computed_at` defaults to `now()`, which returns the SAME value
for every statement inside one Postgres transaction (transaction time, not
statement time). Any action that writes more than one version in a single
transaction -- e.g. POST /rollback/{version_id} recovering a multi-node
dependency chain -- calls `services/merkle.compute_and_store_root` once per
write, producing several `merkle_roots` rows that all share one
`computed_at`. `latest_root()`'s tiebreak on `root_id` (a random UUID, with
no relationship to insertion order) then has roughly 1-in-N odds of picking
a transient mid-transaction root instead of the true final one -- caught
live via `POST /integrity/verify` falsely reporting `tampered: true` right
after a clean 3-node rollback, with `row_mismatches` empty (no row was
actually tampered) but `root_mismatch: true` against a stale root.

A real monotonic sequence removes the ambiguity: `nextval()` is called once
per row at insert time regardless of transaction boundaries, so ordering by
it (instead of computed_at + root_id) always recovers true insertion order.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8b2e5f6a1c9d'
down_revision: Union[str, None] = '4f1a9b3c7d2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE merkle_roots_sequence_number_seq")
    op.add_column(
        "merkle_roots",
        sa.Column(
            "sequence_number",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("nextval('merkle_roots_sequence_number_seq')"),
        ),
    )
    op.execute("ALTER SEQUENCE merkle_roots_sequence_number_seq OWNED BY merkle_roots.sequence_number")
    op.create_index("ix_merkle_roots_sequence_number", "merkle_roots", ["sequence_number"])


def downgrade() -> None:
    op.drop_index("ix_merkle_roots_sequence_number", table_name="merkle_roots")
    op.drop_column("merkle_roots", "sequence_number")
    op.execute("DROP SEQUENCE IF EXISTS merkle_roots_sequence_number_seq")
