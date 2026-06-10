"""Governance enum widenings for enum-gap escalation (issue 48)

Adds:
- Action.suggest_enum_addition
- TargetType.enum_value
- ValidationStatus.declined_by_operator
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_ACTION_VALUES_V3 = (
    "insert",
    "update",
    "deactivate",
    "create_file",
    "modify_file",
    "run_test",
    "validate",
    "suggest_human_apply",
    "suggest_enum_addition",
)

_ACTION_VALUES_V2 = (
    "insert",
    "update",
    "deactivate",
    "create_file",
    "modify_file",
    "run_test",
    "validate",
    "suggest_human_apply",
)

_TARGET_TYPE_VALUES_V3 = (
    "concepts",
    "series",
    "series_families",
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
    "series_family_members",
    "geography_memberships",
    "enum_value",
)

_TARGET_TYPE_VALUES_V2 = (
    "concepts",
    "series",
    "series_families",
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
    "series_family_members",
    "geography_memberships",
)

_VALIDATION_STATUS_VALUES_V3 = (
    "pending",
    "passed",
    "failed",
    "warning",
    "not_required",
    "pending_human_apply",
    "applied_by_operator",
    "declined_by_operator",
)

_VALIDATION_STATUS_VALUES_V2 = (
    "pending",
    "passed",
    "failed",
    "warning",
    "not_required",
    "pending_human_apply",
    "applied_by_operator",
)


def upgrade() -> None:
    _action_len = max(len(v) for v in _ACTION_VALUES_V3)
    _target_len = max(len(v) for v in _TARGET_TYPE_VALUES_V3)
    _vs_len = max(len(v) for v in _VALIDATION_STATUS_VALUES_V3)

    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN action TYPE VARCHAR({_action_len})"
    )
    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN target_type TYPE VARCHAR({_target_len})"
    )
    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN validation_status TYPE VARCHAR({_vs_len})"
    )

    op.drop_constraint(
        "ck_change_proposal_items_action",
        "change_proposal_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_change_proposal_items_action",
        "change_proposal_items",
        sa.Column("action").in_(_ACTION_VALUES_V3),
    )

    op.drop_constraint(
        "ck_change_proposal_items_target_type",
        "change_proposal_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_change_proposal_items_target_type",
        "change_proposal_items",
        sa.Column("target_type").in_(_TARGET_TYPE_VALUES_V3),
    )

    op.drop_constraint(
        "ck_change_proposal_items_validation_status",
        "change_proposal_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_change_proposal_items_validation_status",
        "change_proposal_items",
        sa.Column("validation_status").in_(_VALIDATION_STATUS_VALUES_V3),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_change_proposal_items_validation_status",
        "change_proposal_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_change_proposal_items_validation_status",
        "change_proposal_items",
        sa.Column("validation_status").in_(_VALIDATION_STATUS_VALUES_V2),
    )
    _vs_len_v2 = max(len(v) for v in _VALIDATION_STATUS_VALUES_V2)
    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN validation_status TYPE VARCHAR({_vs_len_v2})"
    )

    op.drop_constraint(
        "ck_change_proposal_items_target_type",
        "change_proposal_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_change_proposal_items_target_type",
        "change_proposal_items",
        sa.Column("target_type").in_(_TARGET_TYPE_VALUES_V2),
    )
    _target_len_v2 = max(len(v) for v in _TARGET_TYPE_VALUES_V2)
    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN target_type TYPE VARCHAR({_target_len_v2})"
    )

    op.drop_constraint(
        "ck_change_proposal_items_action",
        "change_proposal_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_change_proposal_items_action",
        "change_proposal_items",
        sa.Column("action").in_(_ACTION_VALUES_V2),
    )
    _action_len_v2 = max(len(v) for v in _ACTION_VALUES_V2)
    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN action TYPE VARCHAR({_action_len_v2})"
    )
