"""Drop series.is_default (ADR 0027 — defer the default-reading marker).

ADR 0027 reverses the ADR 0025 §1 decision to materialize
`indicator_variants.is_default` as `series.is_default`. The boolean was an
unenforced, advisory flag (no partial-unique, absent from the admin surface) that
disambiguated nothing while every concept+geography slice carried a single series.
It is deferred until a real multi-series `(category_id, geography_id)` slice needs
a headline-reading marker, at which point it returns under its own ADR.

`category_id` (added alongside it in 0019) is unaffected. Upgrade drops the column;
downgrade re-adds it at its 0019 shape (NOT NULL, server_default false) for a clean
round-trip.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("series", "is_default")


def downgrade() -> None:
    op.add_column(
        "series",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
