"""drop ivfflat embedding index -- approximate ANN misses rows at demo scale

Revision ID: 4f1a9b3c7d2e
Revises: 7c1c4e9f2a3b
Create Date: 2026-07-28 20:00:00.000000

pgvector's ivfflat index defaults to 100 lists (clusters) and probes only 1
of them per query. Built over a handful of demo-scale rows (DESIGN.md's own
non-goals: "production-scale vector search... pgvector is enough" implies a
small table, not millions of rows), nearly every cluster ends up empty, so
Postgres's planner -- which switches from a sequential scan to
`Index Scan using ix_memory_versions_embedding` the moment an
`ORDER BY embedding <=> :query LIMIT :k` shape appears -- silently returns
fewer rows than actually match, sometimes zero, even when a query's
embedding is identical to a stored one. Confirmed via `EXPLAIN` and by
toggling `enable_indexscan` locally: the index, not the query, drops rows.

At this project's scale a sequential scan computing exact cosine distance
over every active version is both correct and fast -- there's no
approximate-search benefit worth trading correctness for. Drop the index
rather than tune `lists`/`probes`, since any `lists` value would need
retuning as the demo's row count changes and an exact scan has no such
knob to get wrong.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4f1a9b3c7d2e'
down_revision: Union[str, None] = '7c1c4e9f2a3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_memory_versions_embedding", table_name="memory_versions")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX ix_memory_versions_embedding ON memory_versions "
        "USING ivfflat (embedding vector_cosine_ops)"
    )
