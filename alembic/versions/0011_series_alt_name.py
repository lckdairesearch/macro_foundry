"""Add series.alt_name for curated series aliases.

Mirrors the existing alt_name columns on providers and geographies.
Curated, provider-agnostic search aid; distinct from
series_sources.external_name which carries per-provider titles for
audit and reconciliation.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "series",
        sa.Column("alt_name", sa.ARRAY(sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("series", "alt_name")
