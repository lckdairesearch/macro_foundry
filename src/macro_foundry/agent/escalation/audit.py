"""Audit-row emission helpers for escalation gaps."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

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


class ChangeProposalStore(Protocol):
    """Persistence seam for change proposal audit rows."""

    async def create_change_proposal(self, payload: dict[str, Any]) -> str | uuid.UUID:
        """Create a change_proposals row and return its id."""

    async def create_change_proposal_item(self, payload: dict[str, Any]) -> str | uuid.UUID:
        """Create a change_proposal_items row and return its id."""


class GapAuditEmission(BaseModel):
    """Identifiers returned after emitting one gap audit proposal."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str | uuid.UUID
    item_id: str | uuid.UUID


async def emit_gap_audit_row(
    *,
    store: ChangeProposalStore,
    title: str,
    rationale: str,
    proposal_type: ProposalType,
    proposal_status: ProposalStatus,
    requested_by: RequestedBy,
    risk_level: RiskLevel,
    item_type: ItemType,
    target_type: TargetType,
    action: Action,
    proposed_data: dict[str, Any],
    validation_status: ValidationStatus,
    target_id: uuid.UUID | None = None,
    target_ref: str | None = None,
    diff_summary: str | None = None,
    validation_notes: str | None = None,
    created_by_agent: str | None = "macrodb-onboarding",
    user_prompt: str | None = None,
    review_notes: str | None = None,
) -> GapAuditEmission:
    """Emit one independent change_proposals audit row for one escalation gap."""

    proposal_id = await store.create_change_proposal(
        {
            "title": title,
            "proposal_type": proposal_type,
            "status": proposal_status,
            "requested_by": requested_by,
            "created_by_agent": created_by_agent,
            "user_prompt": user_prompt,
            "rationale": rationale,
            "risk_level": risk_level,
            "review_notes": review_notes,
        },
    )
    item_id = await store.create_change_proposal_item(
        {
            "proposal_id": proposal_id,
            "item_type": item_type,
            "target_type": target_type,
            "action": action,
            "target_id": target_id,
            "target_ref": target_ref,
            "proposed_data": proposed_data,
            "diff_summary": diff_summary,
            "validation_status": validation_status,
            "validation_notes": validation_notes,
        },
    )
    return GapAuditEmission(proposal_id=proposal_id, item_id=item_id)


__all__ = [
    "ChangeProposalStore",
    "GapAuditEmission",
    "emit_gap_audit_row",
]
