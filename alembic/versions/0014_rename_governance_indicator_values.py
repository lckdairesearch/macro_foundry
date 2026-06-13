"""Rename governance stored-enum values for the indicator rename (issue 69)

Brings the governance audit vocabulary in line with the ``series_family ->
indicator`` table rename (#68). These string values are *persisted* under named
CHECK constraints (no native PG enums), so this is a stored-data change distinct
from the table rename in 0013:

- change_proposal_items.target_type  series_families       -> indicators
- change_proposal_items.target_type  series_family_members -> indicator_variants
- change_proposals.proposal_type      add_family            -> add_indicator

Follows the ADR-0014 enum-gap pattern: widen each named CHECK constraint to the
union of old and new values, data-migrate existing rows old->new, then tighten
the CHECK to the new value set. No VARCHAR widening is needed -- the renamed
values are no longer than the existing maxima (``geography_memberships`` for
target_type, ``add_provider_series`` for proposal_type).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

# change_proposal_items.target_type
_TARGET_TYPE_BASE = (
    "concepts",
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
    "tags",
    "geography_memberships",
    "credential_ref",
    "enum_value",
)
_TARGET_TYPE_OLD = (*_TARGET_TYPE_BASE, "series_families", "series_family_members")
_TARGET_TYPE_NEW = (*_TARGET_TYPE_BASE, "indicators", "indicator_variants")
_TARGET_TYPE_UNION = (*_TARGET_TYPE_BASE, "series_families", "series_family_members", "indicators", "indicator_variants")

# change_proposals.proposal_type
_PROPOSAL_TYPE_BASE = (
    "add_provider_series",
    "add_derived_series",
    "add_concept",
    "code_and_db_change",
    "schema_change",
    "mixed",
)
_PROPOSAL_TYPE_OLD = (*_PROPOSAL_TYPE_BASE, "add_family")
_PROPOSAL_TYPE_NEW = (*_PROPOSAL_TYPE_BASE, "add_indicator")
_PROPOSAL_TYPE_UNION = (*_PROPOSAL_TYPE_BASE, "add_family", "add_indicator")


def _recreate_check(constraint: str, table: str, column: str, values: tuple[str, ...]) -> None:
    op.drop_constraint(constraint, table, type_="check")
    op.create_check_constraint(constraint, table, sa.Column(column).in_(values))


def upgrade() -> None:
    # 1. Widen both CHECK constraints to accept old and new values.
    _recreate_check(
        "ck_change_proposal_items_target_type",
        "change_proposal_items",
        "target_type",
        _TARGET_TYPE_UNION,
    )
    _recreate_check(
        "ck_change_proposals_proposal_type",
        "change_proposals",
        "proposal_type",
        _PROPOSAL_TYPE_UNION,
    )

    # 2. Data-migrate existing rows old -> new.
    op.execute(
        "UPDATE change_proposal_items SET target_type = 'indicators' "
        "WHERE target_type = 'series_families'"
    )
    op.execute(
        "UPDATE change_proposal_items SET target_type = 'indicator_variants' "
        "WHERE target_type = 'series_family_members'"
    )
    op.execute(
        "UPDATE change_proposals SET proposal_type = 'add_indicator' "
        "WHERE proposal_type = 'add_family'"
    )

    # 3. Tighten both CHECK constraints to the new value set only.
    _recreate_check(
        "ck_change_proposal_items_target_type",
        "change_proposal_items",
        "target_type",
        _TARGET_TYPE_NEW,
    )
    _recreate_check(
        "ck_change_proposals_proposal_type",
        "change_proposals",
        "proposal_type",
        _PROPOSAL_TYPE_NEW,
    )


def downgrade() -> None:
    # 1. Widen both CHECK constraints to accept old and new values.
    _recreate_check(
        "ck_change_proposal_items_target_type",
        "change_proposal_items",
        "target_type",
        _TARGET_TYPE_UNION,
    )
    _recreate_check(
        "ck_change_proposals_proposal_type",
        "change_proposals",
        "proposal_type",
        _PROPOSAL_TYPE_UNION,
    )

    # 2. Data-migrate existing rows new -> old.
    op.execute(
        "UPDATE change_proposal_items SET target_type = 'series_families' "
        "WHERE target_type = 'indicators'"
    )
    op.execute(
        "UPDATE change_proposal_items SET target_type = 'series_family_members' "
        "WHERE target_type = 'indicator_variants'"
    )
    op.execute(
        "UPDATE change_proposals SET proposal_type = 'add_family' "
        "WHERE proposal_type = 'add_indicator'"
    )

    # 3. Tighten both CHECK constraints to the old value set only.
    _recreate_check(
        "ck_change_proposal_items_target_type",
        "change_proposal_items",
        "target_type",
        _TARGET_TYPE_OLD,
    )
    _recreate_check(
        "ck_change_proposals_proposal_type",
        "change_proposals",
        "proposal_type",
        _PROPOSAL_TYPE_OLD,
    )
