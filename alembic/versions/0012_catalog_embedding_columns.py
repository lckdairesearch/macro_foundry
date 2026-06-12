"""Add catalog embedding columns and vector indexes."""

from __future__ import annotations

from alembic import op


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    for table_name in ("concepts", "series_families", "series"):
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN embedding vector(1536)")
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN embedding_model text")
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN embedding_input_hash text")
        op.execute(
            " ".join(
                [
                    f"CREATE INDEX ix_{table_name}_embedding_hnsw",
                    f"ON {table_name}",
                    "USING hnsw (embedding vector_cosine_ops)",
                ],
            ),
        )


def downgrade() -> None:
    for table_name in ("series", "series_families", "concepts"):
        op.execute(f"DROP INDEX IF EXISTS ix_{table_name}_embedding_hnsw")
        op.execute(f"ALTER TABLE {table_name} DROP COLUMN embedding_input_hash")
        op.execute(f"ALTER TABLE {table_name} DROP COLUMN embedding_model")
        op.execute(f"ALTER TABLE {table_name} DROP COLUMN embedding")
