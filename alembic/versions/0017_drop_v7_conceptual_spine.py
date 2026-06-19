"""Drop the V7 conceptual spine (concepts / indicators / indicator_variants / tags / concept_tags).

ADR 0025 §1 collapses the conceptual spine into a `categories` tree. This slice
(issue #78) is the destructive half: drop the five V7 tables and retire their
governance vocabulary. It is a drop-and-rebootstrap, not a data migration -- the
catalog is regenerable from `bootstrap/` + `services/registration.py`. The new
`categories` / `category_edges` / `source_groups` tables and the replacement
governance values (`categories`, `source_groups`) land in a later slice.

Governance CHECK changes (widen -> tighten, per the ADR-0014 enum-gap pattern):
- change_proposal_items.target_type  drop {concepts, indicators, tags, indicator_variants}
- change_proposals.proposal_type      drop {add_indicator, add_concept}

No governance rows are silently deleted: the audit tables are assumed to carry
none of the dropped vocabulary, which holds under ADR 0025's reset/reseed/
rebootstrap workflow. If a populated database trips the tighten, that is a
deliberate, loud signal to clear the stale audit rows first.

The downgrade faithfully recreates the five tables at their pre-drop (head)
shape -- embedding columns + HNSW indexes on `concepts`/`indicators`, the
`tags.code` natural key, the renamed indicator constraints -- so an
upgrade/downgrade round-trip is clean.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


# --- governance CHECK value sets ------------------------------------------------

_TARGET_TYPE_NEW = (
    "series",
    "series_sources",
    "ingestion_feeds",
    "file",
    "function",
    "test",
    "providers",
    "provider_catalogs",
    "derived_series",
    "derivation_inputs",
    "geographies",
    "geography_memberships",
    "credential_ref",
    "enum_value",
)
_TARGET_TYPE_DROPPED = ("concepts", "indicators", "tags", "indicator_variants")
_TARGET_TYPE_OLD = (*_TARGET_TYPE_NEW, *_TARGET_TYPE_DROPPED)

_PROPOSAL_TYPE_NEW = (
    "add_provider_series",
    "add_derived_series",
    "code_and_db_change",
    "schema_change",
    "mixed",
)
_PROPOSAL_TYPE_DROPPED = ("add_indicator", "add_concept")
_PROPOSAL_TYPE_OLD = (*_PROPOSAL_TYPE_NEW, *_PROPOSAL_TYPE_DROPPED)


def _recreate_check(constraint: str, table: str, column: str, values: tuple[str, ...]) -> None:
    op.drop_constraint(constraint, table, type_="check")
    op.create_check_constraint(constraint, table, sa.Column(column).in_(values))


def _set_governance_checks(target_type: tuple[str, ...], proposal_type: tuple[str, ...]) -> None:
    _recreate_check(
        "ck_change_proposal_items_target_type",
        "change_proposal_items",
        "target_type",
        target_type,
    )
    _recreate_check(
        "ck_change_proposals_proposal_type",
        "change_proposals",
        "proposal_type",
        proposal_type,
    )


def upgrade() -> None:
    # Drop the five spine tables in FK-safe order (dependents first). Dropping a
    # table drops its indexes (incl. HNSW) and constraints automatically.
    op.drop_table("concept_tags")
    op.drop_table("indicator_variants")
    op.drop_table("indicators")
    op.drop_table("concepts")
    op.drop_table("tags")

    # Tighten the governance CHECKs to drop the now-dead vocabulary.
    _set_governance_checks(_TARGET_TYPE_NEW, _PROPOSAL_TYPE_NEW)


def downgrade() -> None:
    # Re-admit the dropped governance vocabulary first.
    _set_governance_checks(_TARGET_TYPE_OLD, _PROPOSAL_TYPE_OLD)

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # concepts (0001 + 0012 embedding columns/index).
    op.create_table(
        "concepts",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding_input_hash", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_concepts_code"),
    )
    op.execute("ALTER TABLE concepts ADD COLUMN embedding vector(1536)")
    op.execute("CREATE INDEX ix_concepts_embedding_hnsw ON concepts USING hnsw (embedding vector_cosine_ops)")

    # tags (0001 + 0015 code natural key replacing the name unique).
    op.create_table(
        "tags",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_tags_code"),
    )

    # indicators (0001 series_families, renamed in 0013 + 0012 embedding columns/index).
    op.create_table(
        "indicators",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("concept_id", sa.UUID(), nullable=False),
        sa.Column("geography_id", sa.UUID(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding_input_hash", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["geography_id"], ["geographies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_indicators_code"),
    )
    op.execute("ALTER TABLE indicators ADD COLUMN embedding vector(1536)")
    op.execute("CREATE INDEX ix_indicators_embedding_hnsw ON indicators USING hnsw (embedding vector_cosine_ops)")

    # concept_tags (0016 composite-PK junction with CASCADE FKs).
    op.create_table(
        "concept_tags",
        sa.Column("concept_id", UUID(as_uuid=True), sa.ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", UUID(as_uuid=True), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    # indicator_variants (0001 series_family_members, renamed in 0013).
    op.create_table(
        "indicator_variants",
        sa.Column("indicator_id", sa.UUID(), nullable=False),
        sa.Column("series_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["indicator_id"], ["indicators.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("indicator_id", "series_id"),
        sa.UniqueConstraint("series_id", name="uq_indicator_variants_series_id"),
    )
