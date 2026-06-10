"""Governance enum widenings and change_proposals new columns (issue 47)

Adds:
- change_proposals.source_agent_session_id
- change_proposals.applied_by
- Widens ck_change_proposal_items_action to include suggest_human_apply
- Widens ck_change_proposal_items_validation_status to include
  pending_human_apply and applied_by_operator
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

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

_ACTION_VALUES_V1 = (
    "insert",
    "update",
    "deactivate",
    "create_file",
    "modify_file",
    "run_test",
    "validate",
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

_VALIDATION_STATUS_VALUES_V1 = (
    "pending",
    "passed",
    "failed",
    "warning",
    "not_required",
)


def upgrade() -> None:
    op.add_column(
        "change_proposals",
        sa.Column("source_agent_session_id", sa.String(), nullable=True),
    )
    op.add_column(
        "change_proposals",
        sa.Column("applied_by", sa.String(), nullable=True),
    )

    # Widen VARCHAR columns so the new longer enum values fit.
    _action_len = max(len(v) for v in _ACTION_VALUES_V2)
    _vs_len = max(len(v) for v in _VALIDATION_STATUS_VALUES_V2)
    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN action TYPE VARCHAR({_action_len})"
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
        sa.Column("action").in_(_ACTION_VALUES_V2),
    )

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


def downgrade() -> None:
    op.drop_constraint(
        "ck_change_proposal_items_validation_status",
        "change_proposal_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_change_proposal_items_validation_status",
        "change_proposal_items",
        sa.Column("validation_status").in_(_VALIDATION_STATUS_VALUES_V1),
    )
    _vs_len_v1 = max(len(v) for v in _VALIDATION_STATUS_VALUES_V1)
    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN validation_status TYPE VARCHAR({_vs_len_v1})"
    )

    op.drop_constraint(
        "ck_change_proposal_items_action",
        "change_proposal_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_change_proposal_items_action",
        "change_proposal_items",
        sa.Column("action").in_(_ACTION_VALUES_V1),
    )
    _action_len_v1 = max(len(v) for v in _ACTION_VALUES_V1)
    op.execute(
        f"ALTER TABLE change_proposal_items ALTER COLUMN action TYPE VARCHAR({_action_len_v1})"
    )

    op.drop_column("change_proposals", "applied_by")
    op.drop_column("change_proposals", "source_agent_session_id")
