"""Add catalog embedding columns and HNSW indexes."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


EMBEDDED_TABLES = ("concepts", "series_families", "series")
INDEX_NAMES = {
    "concepts": "ix_concepts_embedding_hnsw",
    "series_families": "ix_series_families_embedding_hnsw",
    "series": "ix_series_embedding_hnsw",
}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    for table_name in EMBEDDED_TABLES:
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN embedding vector(1536)")
        op.add_column(
            table_name,
            sa.Column("embedding_model", sa.Text(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("embedding_input_hash", sa.Text(), nullable=True),
        )
        op.execute(
            f"""
            CREATE INDEX {INDEX_NAMES[table_name]}
            ON {table_name}
            USING hnsw (embedding vector_cosine_ops)
            """,
        )


def downgrade() -> None:
    for table_name in reversed(EMBEDDED_TABLES):
        op.execute(f"DROP INDEX IF EXISTS {INDEX_NAMES[table_name]}")
        op.drop_column(table_name, "embedding_input_hash")
        op.drop_column(table_name, "embedding_model")
        op.execute(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS embedding")
