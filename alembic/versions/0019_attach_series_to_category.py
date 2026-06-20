"""Attach series to a category node (series.category_id + series.is_default).

ADR 0025 §3 (issue #80): a series attaches to its most-specific concept node.
This slice adds two columns to `series`:

- `category_id` — a NULLABLE FK -> categories.id with ON DELETE RESTRICT. Null is
  deliberate (draft / unclassified series). The "concept-only, never a topic"
  rule is enforced APP-SIDE (Pydantic + service), not by a DB constraint
  (ADR 0025 §3 / db_er.txt line 425).
- `is_default` — NOT NULL boolean, server_default false. The default reading
  within (category_id, geography_id); the former indicator_variants.is_default.
  No partial-unique index is enforced (db_er.txt line 142).

The derived "indicator" grain is the query `(category_id, geography_id)`; it is
not a stored row.

Self-contained: assumes only `series` and `categories` exist at down_revision
0018. Upgrade/downgrade round-trips.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "series",
        sa.Column("category_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "series",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_foreign_key(
        "fk_series_category_id_categories",
        "series",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_series_category_id_categories", "series", type_="foreignkey")
    op.drop_column("series", "is_default")
    op.drop_column("series", "category_id")
