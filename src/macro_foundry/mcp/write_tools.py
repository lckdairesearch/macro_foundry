"""Write-enabled macrodb MCP tool implementations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from macro_foundry.models import ChangeProposal, ChangeProposalItem
from macro_foundry.schemas._base import SchemaModel


class ProposeCreateSeriesArgs(SchemaModel):
    """Arguments for propose_create_series."""

    session_id: str
    payload: dict[str, Any]
    rationale: str | None = None


class ApplyApprovedProposalArgs(SchemaModel):
    """Arguments for apply_approved_proposal."""

    approved_proposal_id: UUID


class TriggerFeedExecutionArgs(SchemaModel):
    """Arguments for trigger_feed_execution."""

    feed_id: UUID


class RecordSuggestHumanApplyArgs(SchemaModel):
    """Arguments for record_suggest_human_apply."""

    items: list[dict[str, Any]]
    session_id: str
    proposal_id: UUID | None = None


class RecordEnumGapProposalArgs(SchemaModel):
    """Arguments for record_enum_gap_proposal."""

    gap: dict[str, Any]
    session_id: str


class RecordCredentialGapProposalArgs(SchemaModel):
    """Arguments for record_credential_gap_proposal."""

    gap: dict[str, Any]
    session_id: str


class MarkProposalOutcomeArgs(SchemaModel):
    """Arguments for mark_proposal_outcome."""

    proposal_id: UUID
    status: str
    applied_value: str | None = None
    rationale: str | None = None
    applied_by: str | None = None


class MacrodbWriteTools:
    """Write-enabled catalog operations for the onboarding agent."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def propose_create_series(self, args: ProposeCreateSeriesArgs) -> dict[str, Any]:
        proposal = ChangeProposal(
            title=f"Onboarding proposal — session {args.session_id}",
            proposal_type=ProposalType.ADD_PROVIDER_SERIES,
            status=ProposalStatus.PROPOSED,
            requested_by=RequestedBy.AGENT,
            risk_level=RiskLevel.LOW,
            rationale=args.rationale,
            source_agent_session_id=args.session_id,
            created_by_agent="onboarding_agent",
        )
        self._session.add(proposal)
        await self._session.flush()
        item = ChangeProposalItem(
            proposal_id=proposal.id,
            item_type=ItemType.DB_ROW,
            target_type=TargetType.SERIES,
            action=Action.INSERT,
            proposed_data=args.payload,
            validation_status=ValidationStatus.PENDING,
        )
        self._session.add(item)
        await self._session.flush()
        return {"proposal_id": str(proposal.id), "item_id": str(item.id)}

    async def apply_approved_proposal(self, args: ApplyApprovedProposalArgs) -> dict[str, Any]:
        result = await self._session.execute(
            select(ChangeProposal).where(ChangeProposal.id == args.approved_proposal_id)
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            raise ValueError(f"Proposal {args.approved_proposal_id} not found")
        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError(
                f"Proposal {args.approved_proposal_id} is not approved (status={proposal.status.value})"
            )
        proposal.status = ProposalStatus.APPLIED
        proposal.applied_at = datetime.now(timezone.utc)
        await self._session.flush()
        return {"proposal_id": str(proposal.id), "status": proposal.status.value}

    async def trigger_feed_execution(self, args: TriggerFeedExecutionArgs) -> dict[str, Any]:
        # Slice 17 integration point — stub for now.
        return {"feed_id": str(args.feed_id), "triggered": True}

    async def record_suggest_human_apply(
        self, args: RecordSuggestHumanApplyArgs
    ) -> dict[str, Any]:
        if args.proposal_id is None:
            proposal = ChangeProposal(
                title=f"Suggest-human-apply items — session {args.session_id}",
                proposal_type=ProposalType.MIXED,
                status=ProposalStatus.PROPOSED,
                requested_by=RequestedBy.AGENT,
                risk_level=RiskLevel.LOW,
                source_agent_session_id=args.session_id,
                created_by_agent="onboarding_agent",
            )
            self._session.add(proposal)
            await self._session.flush()
            proposal_id = proposal.id
        else:
            proposal_id = args.proposal_id

        item_ids = []
        for item_data in args.items:
            item = ChangeProposalItem(
                proposal_id=proposal_id,
                item_type=ItemType.DB_ROW,
                target_type=TargetType.SERIES,
                action=Action.SUGGEST_HUMAN_APPLY,
                proposed_data=item_data,
                validation_status=ValidationStatus.PENDING_HUMAN_APPLY,
            )
            self._session.add(item)
            await self._session.flush()
            item_ids.append(str(item.id))

        return {"proposal_id": str(proposal_id), "item_ids": item_ids}

    async def record_enum_gap_proposal(
        self, args: RecordEnumGapProposalArgs
    ) -> dict[str, Any]:
        # Slice 14 — writes audit row for enum-gap escalation.
        proposal = ChangeProposal(
            title=f"Enum gap — session {args.session_id}",
            proposal_type=ProposalType.SCHEMA_CHANGE,
            status=ProposalStatus.PROPOSED,
            requested_by=RequestedBy.AGENT,
            risk_level=RiskLevel.MEDIUM,
            source_agent_session_id=args.session_id,
            created_by_agent="onboarding_agent",
        )
        self._session.add(proposal)
        await self._session.flush()
        item = ChangeProposalItem(
            proposal_id=proposal.id,
            item_type=ItemType.CODE_CHANGE,
            target_type=TargetType.FILE,
            action=Action.MODIFY_FILE,
            proposed_data=args.gap,
            validation_status=ValidationStatus.PENDING,
        )
        self._session.add(item)
        await self._session.flush()
        return {"proposal_id": str(proposal.id), "item_id": str(item.id)}

    async def record_credential_gap_proposal(
        self, args: RecordCredentialGapProposalArgs
    ) -> dict[str, Any]:
        # Slice 15 — writes audit row for credential-gap escalation.
        proposal = ChangeProposal(
            title=f"Credential gap — session {args.session_id}",
            proposal_type=ProposalType.MIXED,
            status=ProposalStatus.PROPOSED,
            requested_by=RequestedBy.AGENT,
            risk_level=RiskLevel.HIGH,
            source_agent_session_id=args.session_id,
            created_by_agent="onboarding_agent",
        )
        self._session.add(proposal)
        await self._session.flush()
        item = ChangeProposalItem(
            proposal_id=proposal.id,
            item_type=ItemType.DB_ROW,
            target_type=TargetType.PROVIDERS,
            action=Action.UPDATE,
            proposed_data=args.gap,
            validation_status=ValidationStatus.PENDING,
        )
        self._session.add(item)
        await self._session.flush()
        return {"proposal_id": str(proposal.id), "item_id": str(item.id)}

    async def mark_proposal_outcome(self, args: MarkProposalOutcomeArgs) -> dict[str, Any]:
        result = await self._session.execute(
            select(ChangeProposalItem).where(ChangeProposalItem.id == args.proposal_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"ChangeProposalItem {args.proposal_id} not found")
        item.validation_status = ValidationStatus(args.status)
        if args.applied_value is not None:
            item.validation_notes = args.applied_value
        if args.rationale is not None:
            if item.validation_notes:
                item.validation_notes = f"{item.validation_notes}\n{args.rationale}"
            else:
                item.validation_notes = args.rationale
        if args.status == ValidationStatus.APPLIED_BY_OPERATOR.value:
            if args.applied_by:
                item.proposal.applied_by = args.applied_by
            item.proposal.applied_at = datetime.now(timezone.utc)
        await self._session.flush()
        return {"item_id": str(item.id), "validation_status": item.validation_status.value}


__all__ = [
    "ApplyApprovedProposalArgs",
    "MacrodbWriteTools",
    "MarkProposalOutcomeArgs",
    "ProposeCreateSeriesArgs",
    "RecordCredentialGapProposalArgs",
    "RecordEnumGapProposalArgs",
    "RecordSuggestHumanApplyArgs",
    "TriggerFeedExecutionArgs",
]
