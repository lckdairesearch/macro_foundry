"""Create the V8 categories tree (categories + category_edges).

ADR 0025 §1, §2 collapse the V7 conceptual spine into a single `categories`
tree discriminated by `kind` (topic | concept). This slice (issue #79) is the
constructive half that follows #78's drop: it creates `categories` (the concept
node carries the old `concepts` embedding) and `category_edges` (a strict tree
via `UNIQUE(child_category_id)`), and admits `categories` as a governance
`target_type`.

Out of scope here (later slices): `source_groups` / `source_group_members`,
`series.category_id` / `series.is_default`, and the `add_category` proposal_type.

Constraints follow the settled rules: a named CHECK for `kind` (no native PG
enum), FKs parent ON DELETE RESTRICT / child ON DELETE CASCADE, ORM-side
`onupdate` for `updated_at`. Depth <= 3 and concept-only series attachment are
app-layer conventions, not DB constraints.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


# Governance target_type widened to admit the new catalog identity table. Mirrors
# 0017's value set (the post-drop head) plus `categories`.
_TARGET_TYPE_OLD = (
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
_TARGET_TYPE_NEW = ("categories", *_TARGET_TYPE_OLD)


def _set_target_type_check(values: tuple[str, ...]) -> None:
    op.drop_constraint("ck_change_proposal_items_target_type", "change_proposal_items", type_="check")
    op.create_check_constraint(
        "ck_change_proposal_items_target_type",
        "change_proposal_items",
        sa.Column("target_type").in_(values),
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "categories",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum("topic", "concept", name="ck_categories_kind", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding_input_hash", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_categories_code"),
    )
    # Embedding column + HNSW cosine index (populated for kind=concept).
    op.execute("ALTER TABLE categories ADD COLUMN embedding vector(1536)")
    op.execute("CREATE INDEX ix_categories_embedding_hnsw ON categories USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        "category_edges",
        sa.Column("parent_category_id", sa.UUID(), nullable=False),
        sa.Column("child_category_id", sa.UUID(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["child_category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("child_category_id", name="uq_category_edges_child_category_id"),
        sa.CheckConstraint(
            "parent_category_id != child_category_id",
            name="ck_category_edges_no_self_edge",
        ),
    )

    _set_target_type_check(_TARGET_TYPE_NEW)


def downgrade() -> None:
    _set_target_type_check(_TARGET_TYPE_OLD)

    op.drop_table("category_edges")
    op.execute("DROP INDEX IF EXISTS ix_categories_embedding_hnsw")
    op.drop_table("categories")
