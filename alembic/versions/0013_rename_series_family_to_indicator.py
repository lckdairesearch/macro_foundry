"""Rename series_family -> indicator (ADR 0021).

In-place rename of the catalog's middle rung to measurement-theory vocabulary:

- table  series_families        -> indicators
- table  series_family_members  -> indicator_variants
- column indicator_variants.family_id  -> indicator_id
- column indicator_variants.variant    -> label
- column indicator_variants.is_primary -> is_default

Named primary keys, unique constraints, the two indicator_variants foreign
keys, and the embedding HNSW index are renamed to match. Existing rows and
embeddings are carried forward (no drop-and-recreate). PG18 named NOT NULL
constraints are intentionally left untouched: they are invisible to the ORM
and to autogenerate, are not part of the documented rename mapping, and the
named-not-null catalog feature is PG18-specific (renaming them would risk
Neon portability).
"""

from __future__ import annotations

from alembic import op


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables.
    op.rename_table("series_families", "indicators")
    op.rename_table("series_family_members", "indicator_variants")

    # Columns on the association row.
    op.alter_column("indicator_variants", "family_id", new_column_name="indicator_id")
    op.alter_column("indicator_variants", "variant", new_column_name="label")
    op.alter_column("indicator_variants", "is_primary", new_column_name="is_default")

    # Indicators: primary key + unique + foreign keys + embedding index.
    op.execute("ALTER TABLE indicators RENAME CONSTRAINT series_families_pkey TO indicators_pkey")
    op.execute("ALTER TABLE indicators RENAME CONSTRAINT uq_series_families_code TO uq_indicators_code")
    op.execute(
        "ALTER TABLE indicators RENAME CONSTRAINT series_families_concept_id_fkey TO indicators_concept_id_fkey"
    )
    op.execute(
        "ALTER TABLE indicators RENAME CONSTRAINT series_families_geography_id_fkey TO indicators_geography_id_fkey"
    )
    op.execute("ALTER INDEX ix_series_families_embedding_hnsw RENAME TO ix_indicators_embedding_hnsw")

    # Indicator variants: primary key + unique + the two foreign keys.
    op.execute(
        "ALTER TABLE indicator_variants RENAME CONSTRAINT series_family_members_pkey TO indicator_variants_pkey"
    )
    op.execute(
        "ALTER TABLE indicator_variants "
        "RENAME CONSTRAINT uq_series_family_members_series_id TO uq_indicator_variants_series_id"
    )
    op.execute(
        "ALTER TABLE indicator_variants "
        "RENAME CONSTRAINT series_family_members_family_id_fkey TO indicator_variants_indicator_id_fkey"
    )
    op.execute(
        "ALTER TABLE indicator_variants "
        "RENAME CONSTRAINT series_family_members_series_id_fkey TO indicator_variants_series_id_fkey"
    )


def downgrade() -> None:
    # Indicator variants: foreign keys + unique + primary key.
    op.execute(
        "ALTER TABLE indicator_variants "
        "RENAME CONSTRAINT indicator_variants_series_id_fkey TO series_family_members_series_id_fkey"
    )
    op.execute(
        "ALTER TABLE indicator_variants "
        "RENAME CONSTRAINT indicator_variants_indicator_id_fkey TO series_family_members_family_id_fkey"
    )
    op.execute(
        "ALTER TABLE indicator_variants "
        "RENAME CONSTRAINT uq_indicator_variants_series_id TO uq_series_family_members_series_id"
    )
    op.execute(
        "ALTER TABLE indicator_variants RENAME CONSTRAINT indicator_variants_pkey TO series_family_members_pkey"
    )

    # Indicators: embedding index + foreign keys + unique + primary key.
    op.execute("ALTER INDEX ix_indicators_embedding_hnsw RENAME TO ix_series_families_embedding_hnsw")
    op.execute(
        "ALTER TABLE indicators RENAME CONSTRAINT indicators_geography_id_fkey TO series_families_geography_id_fkey"
    )
    op.execute(
        "ALTER TABLE indicators RENAME CONSTRAINT indicators_concept_id_fkey TO series_families_concept_id_fkey"
    )
    op.execute("ALTER TABLE indicators RENAME CONSTRAINT uq_indicators_code TO uq_series_families_code")
    op.execute("ALTER TABLE indicators RENAME CONSTRAINT indicators_pkey TO series_families_pkey")

    # Columns on the association row.
    op.alter_column("indicator_variants", "is_default", new_column_name="is_primary")
    op.alter_column("indicator_variants", "label", new_column_name="variant")
    op.alter_column("indicator_variants", "indicator_id", new_column_name="family_id")

    # Tables.
    op.rename_table("indicator_variants", "series_family_members")
    op.rename_table("indicators", "series_families")
