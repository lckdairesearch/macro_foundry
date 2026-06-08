"""Governance SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String
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
from macro_foundry.models._schema_policy import enum_column, fk_uuid


class ChangeProposal(TimestampedBase):
    """Governance proposal row."""

    __tablename__ = "change_proposals"

    title: Mapped[str] = mapped_column(String(), nullable=False)
    proposal_type: Mapped[ProposalType] = enum_column(
        "change_proposals",
        "proposal_type",
        ProposalType,
        nullable=False,
    )
    status: Mapped[ProposalStatus] = enum_column(
        "change_proposals",
        "status",
        ProposalStatus,
        nullable=False,
    )
    requested_by: Mapped[RequestedBy] = enum_column(
        "change_proposals",
        "requested_by",
        RequestedBy,
        nullable=False,
    )
    created_by_agent: Mapped[str | None] = mapped_column(String(), nullable=True)
    user_prompt: Mapped[str | None] = mapped_column(String(), nullable=True)
    rationale: Mapped[str | None] = mapped_column(String(), nullable=True)
    risk_level: Mapped[RiskLevel] = enum_column(
        "change_proposals",
        "risk_level",
        RiskLevel,
        nullable=False,
    )
    review_notes: Mapped[str | None] = mapped_column(String(), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_proposal_id: Mapped[uuid.UUID | None] = fk_uuid(
        "change_proposals.id",
        ondelete="RESTRICT",
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

    proposal_id: Mapped[uuid.UUID] = fk_uuid(
        "change_proposals.id",
        ondelete="CASCADE",
        nullable=False,
    )
    item_type: Mapped[ItemType] = enum_column(
        "change_proposal_items",
        "item_type",
        ItemType,
        nullable=False,
    )
    target_type: Mapped[TargetType] = enum_column(
        "change_proposal_items",
        "target_type",
        TargetType,
        nullable=False,
    )
    action: Mapped[Action] = enum_column(
        "change_proposal_items",
        "action",
        Action,
        nullable=False,
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_ref: Mapped[str | None] = mapped_column(String(), nullable=True)
    proposed_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    diff_summary: Mapped[str | None] = mapped_column(String(), nullable=True)
    validation_status: Mapped[ValidationStatus] = enum_column(
        "change_proposal_items",
        "validation_status",
        ValidationStatus,
        nullable=False,
    )
    validation_notes: Mapped[str | None] = mapped_column(String(), nullable=True)

    proposal: Mapped["ChangeProposal"] = relationship(
        "ChangeProposal",
        back_populates="items",
        lazy="selectin",
    )


__all__ = ["ChangeProposal", "ChangeProposalItem"]
