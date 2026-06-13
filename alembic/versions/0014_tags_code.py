"""Give tags a canonical UPPERCASE `code` natural key.

Brings `tags` into line with the other curated identity tables (`concepts`,
`geographies`, `series`, `indicators`), which key on a stable `code` while
`name` carries display text. Models tags like `concepts` (no `code_standard`).

The `code` UNIQUE constraint replaces the old `name` UNIQUE constraint; `name`
becomes free display text. The obsolete name-keyed taxonomy is dropped: tags are
inert (nothing constructs a `series_tags` row — ADR 0022), so there are no
dependents and this is a clean drop-and-recreate. Reseeding repopulates the
canonical topical taxonomy.

ADR 0022 §2-4. Does not touch the `series_tags` junction (the concept regrain is
a separate slice).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tags", sa.Column("code", sa.Text(), nullable=True))
    op.execute("DELETE FROM tags")
    op.alter_column("tags", "code", nullable=False)

    op.drop_constraint("uq_tags_name", "tags", type_="unique")
    op.create_unique_constraint("uq_tags_code", "tags", ["code"])


def downgrade() -> None:
    op.drop_constraint("uq_tags_code", "tags", type_="unique")
    op.execute("DELETE FROM tags")
    op.create_unique_constraint("uq_tags_name", "tags", ["name"])
    op.drop_column("tags", "code")
