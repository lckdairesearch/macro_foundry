"""Create the V8 provider source-group layer (source_groups + source_group_members).

ADR 0025 §4 adds a provider-side publication layer beside the canonical
`series_hierarchy_edges` decomposition. This slice (issue #81) is the constructive
half: it creates `source_groups` (a typed, self-nesting publication unit owned by a
`provider_catalog`) and `source_group_members` (M:N membership of `series_sources`
in those groups), and admits `source_groups` as a governance `target_type`.

A `series_source` may belong to many groups, so membership is a junction with its
own `UNIQUE(source_group_id, series_source_id)`. Indentation within a group is
DERIVED (intersect membership with `series_hierarchy_edges`); no per-member parent
pointer is stored.

Constraints follow the settled rules: a named CHECK for `group_type` (no native PG
enum), `provider_catalog_id` / `parent_group_id` FKs ON DELETE RESTRICT, member FKs
ON DELETE CASCADE, ORM-side `onupdate` for `updated_at`. A named CHECK forbids a
group being its own parent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


# Governance target_type widened to admit the new provider publication table.
# Mirrors 0018's value set (which already includes `categories`) plus `source_groups`.
_TARGET_TYPE_OLD = (
    "categories",
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
_TARGET_TYPE_NEW = ("source_groups", *_TARGET_TYPE_OLD)


def _set_target_type_check(values: tuple[str, ...]) -> None:
    op.drop_constraint("ck_change_proposal_items_target_type", "change_proposal_items", type_="check")
    op.create_check_constraint(
        "ck_change_proposal_items_target_type",
        "change_proposal_items",
        sa.Column("target_type").in_(values),
    )


def upgrade() -> None:
    op.create_table(
        "source_groups",
        sa.Column("provider_catalog_id", sa.UUID(), nullable=False),
        sa.Column("parent_group_id", sa.UUID(), nullable=True),
        sa.Column(
            "group_type",
            sa.Enum(
                "release",
                "table",
                "dataset",
                "dashboard",
                "other",
                name="ck_source_groups_group_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("code", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["provider_catalog_id"], ["provider_catalogs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_group_id"], ["source_groups.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_catalog_id", "code", name="uq_source_groups_provider_catalog_id_code"),
        sa.CheckConstraint(
            "parent_group_id != id",
            name="ck_source_groups_no_self_parent",
        ),
    )

    op.create_table(
        "source_group_members",
        sa.Column("source_group_id", sa.UUID(), nullable=False),
        sa.Column("series_source_id", sa.UUID(), nullable=False),
        sa.Column("row_label", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_group_id"], ["source_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_source_id"], ["series_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_group_id",
            "series_source_id",
            name="uq_source_group_members_source_group_id_series_source_id",
        ),
    )

    _set_target_type_check(_TARGET_TYPE_NEW)


def downgrade() -> None:
    _set_target_type_check(_TARGET_TYPE_OLD)

    op.drop_table("source_group_members")
    op.drop_table("source_groups")
