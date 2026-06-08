"""Governance-domain Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

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
from macro_foundry.schemas._base import SchemaModel, TimestampedReadSchema


class ChangeProposalBase(SchemaModel):
    """Shared change-proposal fields."""

    title: str
    proposal_type: ProposalType
    status: ProposalStatus
    requested_by: RequestedBy
    created_by_agent: str | None = None
    user_prompt: str | None = None
    rationale: str | None = None
    risk_level: RiskLevel
    review_notes: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    applied_at: datetime | None = None
    superseded_by_proposal_id: UUID | None = None


class ChangeProposalCreate(ChangeProposalBase):
    """Payload for creating a change proposal."""


class ChangeProposalUpdate(SchemaModel):
    """PATCH payload for a change proposal."""

    title: str | None = None
    proposal_type: ProposalType | None = None
    status: ProposalStatus | None = None
    requested_by: RequestedBy | None = None
    created_by_agent: str | None = None
    user_prompt: str | None = None
    rationale: str | None = None
    risk_level: RiskLevel | None = None
    review_notes: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    applied_at: datetime | None = None
    superseded_by_proposal_id: UUID | None = None


class ChangeProposalRead(TimestampedReadSchema, ChangeProposalBase):
    """API read model for a change proposal."""


class ChangeProposalItemBase(SchemaModel):
    """Shared proposal-item fields."""

    proposal_id: UUID
    item_type: ItemType
    target_type: TargetType
    action: Action
    target_id: UUID | None = None
    target_ref: str | None = None
    proposed_data: dict[str, Any] | None = None
    diff_summary: str | None = None
    validation_status: ValidationStatus
    validation_notes: str | None = None


class ChangeProposalItemCreate(ChangeProposalItemBase):
    """Payload for creating a proposal item."""


class ChangeProposalItemUpdate(SchemaModel):
    """PATCH payload for a proposal item."""

    proposal_id: UUID | None = None
    item_type: ItemType | None = None
    target_type: TargetType | None = None
    action: Action | None = None
    target_id: UUID | None = None
    target_ref: str | None = None
    proposed_data: dict[str, Any] | None = None
    diff_summary: str | None = None
    validation_status: ValidationStatus | None = None
    validation_notes: str | None = None


class ChangeProposalItemRead(TimestampedReadSchema, ChangeProposalItemBase):
    """API read model for a proposal item."""


class ChangeProposalReadDetail(ChangeProposalRead):
    """Read model including same-domain proposal items."""

    items: list[ChangeProposalItemRead] = Field(default_factory=list)


__all__ = [
    "ChangeProposalBase",
    "ChangeProposalCreate",
    "ChangeProposalItemBase",
    "ChangeProposalItemCreate",
    "ChangeProposalItemRead",
    "ChangeProposalItemUpdate",
    "ChangeProposalRead",
    "ChangeProposalReadDetail",
    "ChangeProposalUpdate",
]
