"""Credential-gap provider access metadata

Adds:
- providers.auth_scheme
- providers.rate_limit_config
- widens governance CHECK constraints for credential-gap audit rows
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_AUTH_SCHEME_VALUES = (
    "bearer_header",
    "query_param",
    "header_custom",
    "basic_auth",
    "none",
)

_ACTION_VALUES_V3 = (
    "insert",
    "update",
    "deactivate",
    "create_file",
    "modify_file",
    "run_test",
    "validate",
    "suggest_human_apply",
    "suggest_credential_provisioning",
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
    "credential_ref",
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


def _replace_check(table: str, name: str, column: str, values: tuple[str, ...]) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, sa.Column(column).in_(values))


def upgrade() -> None:
    op.add_column(
        "providers",
        sa.Column(
            "auth_scheme",
            sa.Enum(
                *_AUTH_SCHEME_VALUES,
                name="ck_providers_auth_scheme",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "providers",
        sa.Column("rate_limit_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN action TYPE VARCHAR({max(len(v) for v in _ACTION_VALUES_V3)})"
    )
    _replace_check(
        "change_proposal_items",
        "ck_change_proposal_items_action",
        "action",
        _ACTION_VALUES_V3,
    )

    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN target_type TYPE VARCHAR({max(len(v) for v in _TARGET_TYPE_VALUES_V3)})"
    )
    _replace_check(
        "change_proposal_items",
        "ck_change_proposal_items_target_type",
        "target_type",
        _TARGET_TYPE_VALUES_V3,
    )

    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN validation_status TYPE VARCHAR({max(len(v) for v in _VALIDATION_STATUS_VALUES_V3)})"
    )
    _replace_check(
        "change_proposal_items",
        "ck_change_proposal_items_validation_status",
        "validation_status",
        _VALIDATION_STATUS_VALUES_V3,
    )


def downgrade() -> None:
    _replace_check(
        "change_proposal_items",
        "ck_change_proposal_items_validation_status",
        "validation_status",
        _VALIDATION_STATUS_VALUES_V2,
    )
    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN validation_status TYPE VARCHAR({max(len(v) for v in _VALIDATION_STATUS_VALUES_V2)})"
    )

    _replace_check(
        "change_proposal_items",
        "ck_change_proposal_items_target_type",
        "target_type",
        _TARGET_TYPE_VALUES_V2,
    )
    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN target_type TYPE VARCHAR({max(len(v) for v in _TARGET_TYPE_VALUES_V2)})"
    )

    _replace_check(
        "change_proposal_items",
        "ck_change_proposal_items_action",
        "action",
        _ACTION_VALUES_V2,
    )
    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN action TYPE VARCHAR({max(len(v) for v in _ACTION_VALUES_V2)})"
    )

    op.drop_column("providers", "rate_limit_config")
    op.drop_column("providers", "auth_scheme")
