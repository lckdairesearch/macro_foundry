"""Governance SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import TimestampedBase
from macro_foundry.enums import (
    Action,
    ItemType,
    ProposalStatus,
    ProposalType,
    RequestedBy,
    RiskLevel,
    TargetType,
    ValidationStatus,
)


class ChangeProposal(TimestampedBase):
    """Governance proposal row."""

    __tablename__ = "change_proposals"

    title: Mapped[str] = mapped_column(String(), nullable=False)
    proposal_type: Mapped[ProposalType] = mapped_column(
        SAEnum(
            ProposalType,
            native_enum=False,
            name="ck_change_proposals_proposal_type",
            validate_strings=True,
        ),
        nullable=False,
    )
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(
            ProposalStatus,
            native_enum=False,
            name="ck_change_proposals_status",
            validate_strings=True,
        ),
        nullable=False,
    )
    requested_by: Mapped[RequestedBy] = mapped_column(
        SAEnum(
            RequestedBy,
            native_enum=False,
            name="ck_change_proposals_requested_by",
            validate_strings=True,
        ),
        nullable=False,
    )
    created_by_agent: Mapped[str | None] = mapped_column(String(), nullable=True)
    user_prompt: Mapped[str | None] = mapped_column(String(), nullable=True)
    rationale: Mapped[str | None] = mapped_column(String(), nullable=True)
    risk_level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel, native_enum=False, name="ck_change_proposals_risk_level", validate_strings=True),
        nullable=False,
    )
    review_notes: Mapped[str | None] = mapped_column(String(), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("change_proposals.id", ondelete="RESTRICT"),
        nullable=True,
    )

    superseded_by_proposal: Mapped["ChangeProposal | None"] = relationship(
        "ChangeProposal",
        back_populates="superseded_proposals",
        foreign_keys=lambda: [ChangeProposal.superseded_by_proposal_id],
        remote_side=lambda: [ChangeProposal.id],
        lazy="selectin",
    )
    superseded_proposals: Mapped[list["ChangeProposal"]] = relationship(
        "ChangeProposal",
        back_populates="superseded_by_proposal",
        foreign_keys=lambda: [ChangeProposal.superseded_by_proposal_id],
        lazy="selectin",
        passive_deletes=True,
    )
    items: Mapped[list["ChangeProposalItem"]] = relationship(
        "ChangeProposalItem",
        back_populates="proposal",
        lazy="selectin",
        passive_deletes=True,
    )


class ChangeProposalItem(TimestampedBase):
    """Line item attached to one governance proposal."""

    __tablename__ = "change_proposal_items"

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("change_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_type: Mapped[ItemType] = mapped_column(
        SAEnum(ItemType, native_enum=False, name="ck_change_proposal_items_item_type", validate_strings=True),
        nullable=False,
    )
    target_type: Mapped[TargetType] = mapped_column(
        SAEnum(TargetType, native_enum=False, name="ck_change_proposal_items_target_type", validate_strings=True),
        nullable=False,
    )
    action: Mapped[Action] = mapped_column(
        SAEnum(Action, native_enum=False, name="ck_change_proposal_items_action", validate_strings=True),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_ref: Mapped[str | None] = mapped_column(String(), nullable=True)
    proposed_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    diff_summary: Mapped[str | None] = mapped_column(String(), nullable=True)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        SAEnum(
            ValidationStatus,
            native_enum=False,
            name="ck_change_proposal_items_validation_status",
            validate_strings=True,
        ),
        nullable=False,
    )
    validation_notes: Mapped[str | None] = mapped_column(String(), nullable=True)

    proposal: Mapped["ChangeProposal"] = relationship(
        "ChangeProposal",
        back_populates="items",
        lazy="selectin",
    )


__all__ = ["ChangeProposal", "ChangeProposalItem"]
