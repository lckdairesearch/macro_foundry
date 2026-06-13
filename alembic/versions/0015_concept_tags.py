"""Regrain topical tagging from series to concept.

Drops the inert `series_tags` junction (never populated — ADR 0022) and
creates `concept_tags (concept_id, tag_id)` with composite PK and CASCADE FKs.
A series' topical tags are now derived transitively via
`indicator_variant → indicator → concept → concept_tags`.

No data migration: `series_tags` had zero rows.

ADR 0022 §1.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("series_tags")
    op.create_table(
        "concept_tags",
        sa.Column("concept_id", UUID(as_uuid=True), sa.ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", UUID(as_uuid=True), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("concept_tags")
    op.create_table(
        "series_tags",
        sa.Column("series_id", UUID(as_uuid=True), sa.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", UUID(as_uuid=True), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )
