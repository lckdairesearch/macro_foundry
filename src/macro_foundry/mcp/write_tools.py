"""Write-enabled macrodb MCP tool implementations."""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import (
    Action,
    AuthScheme,
    FeedMethod,
    Frequency,
    ItemType,
    Measure,
    MeasureHorizon,
    OriginType,
    PriceBasis,
    ProposalStatus,
    ProposalType,
    ProviderRole,
    ProviderType,
    ReferenceKind,
    RequestedBy,
    RiskLevel,
    SeasonalAdjustment,
    TargetType,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
    ValidationStatus,
)
from macro_foundry.models import (
    ChangeProposal,
    ChangeProposalItem,
    Concept,
    Geography,
    IngestionFeed,
    IngestionFeedMember,
    Provider,
    ProviderCatalog,
    Series,
    SeriesFamily,
    SeriesFamilyMember,
    SeriesHierarchyEdge,
    SeriesSource,
)
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


class ApplyCredentialGapResolutionsArgs(SchemaModel):
    """Arguments for applying resolved credential-gap metadata at Gate 1."""

    resolutions: list[dict[str, Any]]


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
        from macro_foundry.agent.proposal import DraftProposal

        draft = DraftProposal.model_validate(args.payload)
        now = datetime.now(timezone.utc)

        # Resolve geography by code (shared by family and series)
        geography = (
            await self._session.execute(
                select(Geography).where(Geography.code == draft.family.geography_code)
            )
        ).scalar_one_or_none()
        if geography is None:
            raise ValueError(f"Geography {draft.family.geography_code!r} not found")

        # Get or create Concept
        concept = (
            await self._session.execute(
                select(Concept).where(Concept.code == draft.concept.code)
            )
        ).scalar_one_or_none()
        if concept is None:
            if draft.concept.action != "new":
                raise ValueError(f"Concept {draft.concept.code!r} not found")
            concept = Concept(
                code=draft.concept.code,
                name=draft.concept.name,
                description=draft.concept.description,
            )
            self._session.add(concept)
            await self._session.flush()

        # Get or create SeriesFamily
        family = (
            await self._session.execute(
                select(SeriesFamily).where(SeriesFamily.code == draft.family.code)
            )
        ).scalar_one_or_none()
        if family is None:
            if draft.family.action != "new":
                raise ValueError(f"SeriesFamily {draft.family.code!r} not found")
            family = SeriesFamily(
                code=draft.family.code,
                name=draft.family.name,
                description=draft.family.description,
                concept_id=concept.id,
                geography_id=geography.id,
            )
            self._session.add(family)
            await self._session.flush()

        # Create Series
        series = Series(
            code=draft.series.code,
            name=draft.series.name,
            description=draft.series.description,
            origin_type=OriginType(draft.series.origin_type),
            geography_id=geography.id,
            frequency=Frequency(draft.series.frequency),
            temporal_stock_flow=TemporalStockFlow(draft.series.temporal_stock_flow),
            unit_kind=UnitKind(draft.series.unit_kind),
            unit_scale=UnitScale(draft.series.unit_scale),
            measure=Measure(draft.series.measure),
            measure_horizon=MeasureHorizon(draft.series.measure_horizon) if draft.series.measure_horizon else None,
            price_basis=PriceBasis(draft.series.price_basis) if draft.series.price_basis else None,
            currency_code=draft.series.currency_code,
            reference_kind=ReferenceKind(draft.series.reference_kind) if draft.series.reference_kind else None,
            reference_year=draft.series.reference_year,
            reference_label=draft.series.reference_label,
            seasonal_adjustment=SeasonalAdjustment(draft.series.seasonal_adjustment),
            annualized=draft.series.annualized,
            is_active=draft.series.is_active,
            start_date=date_type.fromisoformat(draft.series.start_date) if draft.series.start_date else None,
            end_date=date_type.fromisoformat(draft.series.end_date) if draft.series.end_date else None,
        )
        self._session.add(series)
        await self._session.flush()

        # Create SeriesFamilyMember
        family_member = SeriesFamilyMember(
            family_id=family.id,
            series_id=series.id,
            variant=draft.family_member.variant,
            is_primary=draft.family_member.is_primary,
        )
        self._session.add(family_member)
        await self._session.flush()

        # Resolve Provider → ProviderCatalog by provider name
        provider = (
            await self._session.execute(
                select(Provider).where(Provider.name == draft.source.provider_name)
            )
        ).scalar_one_or_none()
        if provider is None:
            raise ValueError(f"Provider {draft.source.provider_name!r} not found")

        provider_catalog = (
            await self._session.execute(
                select(ProviderCatalog)
                .where(ProviderCatalog.provider_id == provider.id)
                .order_by(ProviderCatalog.is_placeholder)
                .limit(1)
            )
        ).scalar_one_or_none()
        if provider_catalog is None:
            raise ValueError(f"No ProviderCatalog found for provider {draft.source.provider_name!r}")

        # Create SeriesSource
        series_source = SeriesSource(
            series_id=series.id,
            provider_catalog_id=provider_catalog.id,
            external_code=draft.source.external_code,
            external_name=draft.source.external_name,
            priority=draft.source.priority,
            provider_role=ProviderRole(draft.source.provider_role),
        )
        self._session.add(series_source)
        await self._session.flush()

        # Create IngestionFeed + IngestionFeedMember
        feed = IngestionFeed(
            feed_method=FeedMethod(draft.feed.feed_method),
            endpoint_url=draft.feed.fetch_url,
            cron_schedule=draft.feed.cron_schedule,
            is_active=draft.feed.is_active,
        )
        self._session.add(feed)
        await self._session.flush()

        feed_member = IngestionFeedMember(
            ingestion_feed_id=feed.id,
            series_source_id=series_source.id,
            selector_type=draft.feed.selector_type,
            is_active=True,
        )
        self._session.add(feed_member)
        await self._session.flush()

        # Hierarchy edges (parent/child by code; skip if either side not found)
        for edge in draft.hierarchy_edges:
            parent = (
                await self._session.execute(
                    select(Series).where(Series.code == edge.parent_series_code)
                )
            ).scalar_one_or_none()
            child = (
                await self._session.execute(
                    select(Series).where(Series.code == edge.child_series_code)
                )
            ).scalar_one_or_none()
            if parent and child:
                self._session.add(
                    SeriesHierarchyEdge(
                        parent_series_id=parent.id,
                        child_series_id=child.id,
                    )
                )
        if draft.hierarchy_edges:
            await self._session.flush()

        # Audit ChangeProposal (status=APPLIED — Gate 1 already approved)
        audit_proposal = ChangeProposal(
            title=f"Onboarding proposal — session {args.session_id}",
            proposal_type=ProposalType.ADD_PROVIDER_SERIES,
            status=ProposalStatus.APPLIED,
            requested_by=RequestedBy.AGENT,
            risk_level=RiskLevel.LOW,
            rationale=args.rationale,
            source_agent_session_id=args.session_id,
            created_by_agent="onboarding_agent",
            applied_at=now,
        )
        self._session.add(audit_proposal)
        await self._session.flush()

        audit_item = ChangeProposalItem(
            proposal_id=audit_proposal.id,
            item_type=ItemType.DB_ROW,
            target_type=TargetType.SERIES,
            action=Action.INSERT,
            proposed_data={"series_code": series.code, "series_id": str(series.id)},
            validation_status=ValidationStatus.PASSED,
        )
        self._session.add(audit_item)
        await self._session.flush()

        return {
            "proposal_id": str(audit_proposal.id),
            "item_id": str(audit_item.id),
            "series_id": str(series.id),
            "family_id": str(family.id),
            "concept_id": str(concept.id),
            "feed_id": str(feed.id),
        }

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

    async def apply_credential_gap_resolutions(
        self,
        args: ApplyCredentialGapResolutionsArgs,
    ) -> dict[str, Any]:
        updated_provider_ids: list[str] = []
        for resolution in args.resolutions:
            if resolution.get("outcome") not in {"provisioned", "provisioned_renamed"}:
                continue
            provider_identity = resolution.get("provider_identity") or {}
            provider = await self._provider_for_credential_identity(provider_identity)
            provider.credentials_ref = resolution.get("applied_env_var_name")
            auth_scheme = resolution.get("applied_auth_scheme")
            provider.auth_scheme = AuthScheme(auth_scheme) if auth_scheme else None
            provider.rate_limit_config = resolution.get("applied_rate_limit_config")
            await self._session.flush()
            updated_provider_ids.append(str(provider.id))
        return {"provider_ids": updated_provider_ids}

    async def _provider_for_credential_identity(self, provider_identity: dict[str, Any]) -> Provider:
        if provider_identity.get("kind") == "existing":
            provider_id = provider_identity.get("existing_provider_id")
            provider = await self._session.get(Provider, uuid.UUID(provider_id))
            if provider is None:
                raise ValueError(f"Provider {provider_id!r} not found")
            return provider

        provider_name = provider_identity.get("proposed_provider_name")
        if not provider_name:
            raise ValueError("proposed_provider_name is required for new provider identity")
        provider = (
            await self._session.execute(
                select(Provider).where(Provider.name == provider_name)
            )
        ).scalar_one_or_none()
        if provider is not None:
            return provider
        provider = Provider(
            name=provider_name,
            alt_name=None,
            type=ProviderType.OTHER,
            homepage_url=provider_identity.get("proposed_provider_homepage_url"),
            doc_url=provider_identity.get("proposed_provider_doc_url"),
            base_url=None,
            credentials_ref=None,
            auth_scheme=None,
            rate_limit_config=None,
            notes=None,
            is_active=True,
        )
        self._session.add(provider)
        await self._session.flush()
        return provider

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
            target_type=TargetType.CREDENTIAL_REF,
            action=Action.SUGGEST_CREDENTIAL_PROVISIONING,
            proposed_data=args.gap,
            validation_status=ValidationStatus.PENDING_HUMAN_APPLY,
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
    "ApplyCredentialGapResolutionsArgs",
    "MacrodbWriteTools",
    "MarkProposalOutcomeArgs",
    "ProposeCreateSeriesArgs",
    "RecordCredentialGapProposalArgs",
    "RecordEnumGapProposalArgs",
    "RecordSuggestHumanApplyArgs",
    "TriggerFeedExecutionArgs",
]
