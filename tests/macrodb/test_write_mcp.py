"""Tests for write-enabled MCP tools and SQLAdmin mark-applied action (issue 47)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from macro_foundry.agent.catalog import make_apply_catalog_node
from macro_foundry.agent.proposal import (
    DraftConcept,
    DraftFamily,
    DraftFamilyMember,
    DraftIngestionFeed,
    DraftProposal,
    DraftSeries,
    DraftSeriesSource,
    SuggestHumanApplyItem,
)
from macro_foundry.backend.main import admin, app
from macro_foundry.config import settings
from macro_foundry.enums import Action, ItemType, ProposalStatus, ProposalType, RequestedBy, RiskLevel, TargetType, ValidationStatus
from macro_foundry.models import (
    ChangeProposal,
    ChangeProposalItem,
    Concept,
    Geography,
    IngestionFeedMember,
    Provider,
    Series,
    SeriesFamily,
    SeriesFamilyMember,
    SeriesSource,
)
from macro_foundry.mcp.write_tools import (
    ApplyCredentialGapResolutionsArgs,
    ApplyApprovedProposalArgs,
    MacrodbWriteTools,
    MarkProposalOutcomeArgs,
    ProposeCreateSeriesArgs,
    RecordCredentialGapProposalArgs,
    RecordEnumGapProposalArgs,
    RecordSuggestHumanApplyArgs,
)
from macro_foundry.services.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    compose_series_embedding_input,
    hash_embedding_input,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_registration_embed_text(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_embed_text(text: str) -> list[float]:
        fill = float((sum(ord(ch) for ch in text) % 17) + 1)
        return [fill] * EMBEDDING_DIMENSIONS

    monkeypatch.setattr(
        "macro_foundry.services.registration.embed_text",
        fake_embed_text,
    )


def _minimal_draft_payload(series_code: str) -> dict:
    """Minimal valid DraftProposal dict for write-tool tests."""
    return DraftProposal(
        concept=DraftConcept(action="new", code=f"CONCEPT_{series_code}", name=f"Concept {series_code}"),
        family=DraftFamily(
            action="new",
            code=f"FAM_{series_code}",
            name=f"Family {series_code}",
            concept_code=f"CONCEPT_{series_code}",
            geography_code="HKG",
        ),
        series=DraftSeries(
            action="new",
            code=series_code,
            name=f"Series {series_code}",
            frequency="M",
            measure="level",
            unit_kind="index",
            temporal_stock_flow="index",
            unit_scale="one",
            seasonal_adjustment="NSA",
        ),
        source=DraftSeriesSource(
            provider_name="HKG Census and Statistics Department",
            external_code=f"EXT_{series_code}",
        ),
        feed=DraftIngestionFeed(
            selector_type="json_path",
            cron_schedule="0 9 * * *",
            feed_method="api",
        ),
        family_member=DraftFamilyMember(variant=None),
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Write tools DB tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_propose_create_series_writes_proposal_and_item(
    session: AsyncSession,
) -> None:
    tools = MacrodbWriteTools(session)
    result = await tools.propose_create_series(
        ProposeCreateSeriesArgs(
            session_id="sess-test-001",
            payload=_minimal_draft_payload("CPI_HKG_M_TST"),
            rationale="Test",
        )
    )
    assert "proposal_id" in result
    assert "item_id" in result
    assert "series_id" in result

    proposal = (
        await session.execute(
            select(ChangeProposal).where(
                ChangeProposal.source_agent_session_id == "sess-test-001"
            )
        )
    ).scalar_one()
    assert proposal.status == ProposalStatus.APPLIED
    assert proposal.applied_at is not None
    assert proposal.applied_by is None


@pytest.mark.asyncio
async def test_record_suggest_human_apply_writes_pending_items(
    session: AsyncSession,
) -> None:
    tools = MacrodbWriteTools(session)
    result = await tools.record_suggest_human_apply(
        RecordSuggestHumanApplyArgs(
            items=[
                {"schema_field": "concept.name", "proposed_value": "CPI (alt)", "rationale": "test"},
                {"schema_field": "series_family.name", "proposed_value": "CPI HKG (alt)", "rationale": "test2"},
            ],
            session_id="sess-sha-001",
        )
    )
    assert "proposal_id" in result
    assert len(result["item_ids"]) == 2

    items = (
        await session.execute(
            select(ChangeProposalItem).where(
                ChangeProposalItem.action == Action.SUGGEST_HUMAN_APPLY
            )
        )
    ).scalars().all()
    assert len(items) == 2
    for item in items:
        assert item.validation_status == ValidationStatus.PENDING_HUMAN_APPLY


@pytest.mark.asyncio
async def test_record_credential_gap_proposal_writes_credential_ref_audit_item(
    session: AsyncSession,
) -> None:
    tools = MacrodbWriteTools(session)
    result = await tools.record_credential_gap_proposal(
        RecordCredentialGapProposalArgs(
            session_id="sess-credential-001",
            gap={
                "provider_identity": {
                    "kind": "new",
                    "proposed_provider_name": "Example Provider",
                    "proposed_provider_homepage_url": "https://example.test",
                    "proposed_provider_doc_url": "https://example.test/docs",
                },
                "proposed_env_var_name": "EXAMPLE_API_KEY",
                "proposed_auth_scheme": "bearer_header",
                "inferred_rate_limit": {"requests_per_minute": 60},
                "evidence_url": "https://example.test/docs/auth",
                "evidence_snippet": "Use an API key.",
                "rationale": "Provider docs require an API key.",
            },
        )
    )

    item = (
        await session.execute(
            select(ChangeProposalItem).where(
                ChangeProposalItem.id == result["item_id"]
            )
        )
    ).scalar_one()
    assert item.target_type == TargetType.CREDENTIAL_REF
    assert item.action == Action.SUGGEST_CREDENTIAL_PROVISIONING
    assert item.validation_status == ValidationStatus.PENDING_HUMAN_APPLY
    assert item.proposed_data["proposed_env_var_name"] == "EXAMPLE_API_KEY"

    proposal = await session.get(ChangeProposal, item.proposal_id)
    assert proposal is not None
    assert proposal.proposal_type == ProposalType.MIXED
    assert proposal.status == ProposalStatus.PROPOSED
    assert proposal.source_agent_session_id == "sess-credential-001"


@pytest.mark.asyncio
async def test_apply_credential_gap_resolutions_updates_existing_provider_access_metadata(
    session: AsyncSession,
) -> None:
    provider = (
        await session.execute(
            select(Provider).where(Provider.name == "HKG Census and Statistics Department")
        )
    ).scalar_one()
    tools = MacrodbWriteTools(session)

    result = await tools.apply_credential_gap_resolutions(
        ApplyCredentialGapResolutionsArgs(
            resolutions=[
                {
                    "outcome": "provisioned",
                    "provider_identity": {
                        "kind": "existing",
                        "existing_provider_id": str(provider.id),
                    },
                    "applied_env_var_name": "HKG_CENSTATD_API_KEY",
                    "applied_auth_scheme": "bearer_header",
                    "applied_rate_limit_config": {"requests_per_minute": 60},
                }
            ]
        )
    )

    assert result["provider_ids"] == [str(provider.id)]
    refreshed = await session.get(Provider, provider.id)
    assert refreshed is not None
    assert refreshed.credentials_ref == "HKG_CENSTATD_API_KEY"
    assert refreshed.auth_scheme.value == "bearer_header"
    assert refreshed.rate_limit_config == {"requests_per_minute": 60}


@pytest.mark.asyncio
async def test_record_enum_gap_proposal_writes_independent_enum_value_audit_row(
    session: AsyncSession,
) -> None:
    tools = MacrodbWriteTools(session)
    gap = {
        "enum_path": "macro_foundry.enums.series.SeasonalAdjustment",
        "proposed_value": "TCA",
        "proposed_name": "TREND_CYCLE_ADJUSTED",
        "existing_values_considered": {
            "SA": "Seasonally adjusted is not the trend-cycle component.",
            "SAAR": "Annualized seasonal adjustment is not the trend-cycle component.",
            "NSA": "Unadjusted data is not the trend-cycle component.",
            "unknown": "Provider documentation is explicit, not unknown.",
        },
        "provider_evidence": {
            "url": "https://example.test/provider-methodology",
            "snippet": "Trend-cycle adjusted series are published separately.",
        },
        "catalog_impact": "Queries for seasonally adjusted data must not include trend-cycle data.",
        "rationale": "Provider publishes trend-cycle adjusted data as a distinct methodology.",
    }

    result = await tools.record_enum_gap_proposal(
        RecordEnumGapProposalArgs(gap=gap, session_id="sess-enum-gap-001")
    )

    proposal = await session.get(ChangeProposal, result["proposal_id"])
    assert proposal is not None
    assert proposal.proposal_type == ProposalType.SCHEMA_CHANGE
    assert proposal.status == ProposalStatus.PROPOSED
    assert proposal.source_agent_session_id == "sess-enum-gap-001"

    item = await session.get(ChangeProposalItem, result["item_id"])
    assert item is not None
    assert item.item_type == ItemType.CODE_CHANGE
    assert item.target_type == TargetType.ENUM_VALUE
    assert item.action == Action.SUGGEST_ENUM_ADDITION
    assert item.validation_status == ValidationStatus.PENDING
    assert item.proposed_data == gap


@pytest.mark.asyncio
async def test_apply_approved_proposal_validates_status(
    session: AsyncSession,
) -> None:
    tools = MacrodbWriteTools(session)
    create_result = await tools.propose_create_series(
        ProposeCreateSeriesArgs(
            session_id="sess-reject-001",
            payload=_minimal_draft_payload("REJECT_TST_SRS"),
        )
    )
    import uuid

    with pytest.raises(ValueError, match="not approved"):
        await tools.apply_approved_proposal(
            type("Args", (), {"approved_proposal_id": uuid.UUID(create_result["proposal_id"])})()
        )


@pytest.mark.asyncio
async def test_apply_approved_proposal_materializes_concept_with_embeddings(
    session: AsyncSession,
) -> None:
    tools = MacrodbWriteTools(session)
    proposal = ChangeProposal(
        title="approved concept proposal",
        proposal_type=ProposalType.ADD_CONCEPT,
        status=ProposalStatus.APPROVED,
        requested_by=RequestedBy.AGENT,
        risk_level=RiskLevel.LOW,
        source_agent_session_id="sess-apply-concept-001",
        created_by_agent="onboarding_agent",
    )
    session.add(proposal)
    await session.flush()
    session.add(
        ChangeProposalItem(
            proposal_id=proposal.id,
            item_type=ItemType.DB_ROW,
            target_type=TargetType.CONCEPTS,
            action=Action.INSERT,
            proposed_data={
                "code": "APPLIED_CONCEPT_66",
                "name": "Applied Concept 66",
                "description": "Approved concept proposal materialization.",
            },
            validation_status=ValidationStatus.PASSED,
        ),
    )
    await session.flush()

    result = await tools.apply_approved_proposal(
        ApplyApprovedProposalArgs(approved_proposal_id=proposal.id),
    )

    concept = (
        await session.execute(select(Concept).where(Concept.code == "APPLIED_CONCEPT_66"))
    ).scalar_one()
    assert result["status"] == ProposalStatus.APPLIED.value
    assert concept.embedding is not None
    assert concept.embedding_model == EMBEDDING_MODEL
    assert concept.embedding_input_hash is not None


@pytest.mark.asyncio
async def test_apply_approved_proposal_materializes_family_with_embeddings(
    session: AsyncSession,
) -> None:
    tools = MacrodbWriteTools(session)
    concept = Concept(
        code="FAMILY_PARENT_CONCEPT_66",
        name="Family Parent Concept 66",
        description="Parent concept for approved family proposal.",
    )
    session.add(concept)
    await session.flush()
    geography = (
        await session.execute(select(Geography).where(Geography.code == "HKG"))
    ).scalar_one()

    proposal = ChangeProposal(
        title="approved family proposal",
        proposal_type=ProposalType.ADD_FAMILY,
        status=ProposalStatus.APPROVED,
        requested_by=RequestedBy.AGENT,
        risk_level=RiskLevel.LOW,
        source_agent_session_id="sess-apply-family-001",
        created_by_agent="onboarding_agent",
    )
    session.add(proposal)
    await session.flush()
    session.add(
        ChangeProposalItem(
            proposal_id=proposal.id,
            item_type=ItemType.DB_ROW,
            target_type=TargetType.SERIES_FAMILIES,
            action=Action.INSERT,
            proposed_data={
                "code": "APPLIED_FAMILY_66",
                "name": "Applied Family 66",
                "description": "Approved family proposal materialization.",
                "concept_code": concept.code,
                "geography_code": geography.code,
            },
            validation_status=ValidationStatus.PASSED,
        ),
    )
    await session.flush()

    result = await tools.apply_approved_proposal(
        ApplyApprovedProposalArgs(approved_proposal_id=proposal.id),
    )

    family = (
        await session.execute(
            select(SeriesFamily).where(SeriesFamily.code == "APPLIED_FAMILY_66")
        )
    ).scalar_one()
    assert result["status"] == ProposalStatus.APPLIED.value
    assert family.embedding is not None
    assert family.embedding_model == EMBEDDING_MODEL
    assert family.embedding_input_hash is not None


@pytest.mark.asyncio
async def test_apply_approved_proposal_materializes_series_with_current_family_context(
    session: AsyncSession,
) -> None:
    tools = MacrodbWriteTools(session)
    geography = (
        await session.execute(select(Geography).where(Geography.code == "HKG"))
    ).scalar_one()
    concept = Concept(
        code="SERIES_PARENT_CONCEPT_66",
        name="Series Parent Concept 66",
        description="Parent concept for approved series proposal.",
    )
    session.add(concept)
    await session.flush()
    family = SeriesFamily(
        code="SERIES_PARENT_FAMILY_66",
        name="Series Parent Family 66",
        description="Parent family for approved series proposal.",
        concept_id=concept.id,
        geography_id=geography.id,
    )
    session.add(family)
    await session.flush()

    proposal = ChangeProposal(
        title="approved series proposal",
        proposal_type=ProposalType.ADD_PROVIDER_SERIES,
        status=ProposalStatus.APPROVED,
        requested_by=RequestedBy.AGENT,
        risk_level=RiskLevel.LOW,
        source_agent_session_id="sess-apply-series-001",
        created_by_agent="onboarding_agent",
    )
    session.add(proposal)
    await session.flush()
    session.add_all(
        [
            ChangeProposalItem(
                proposal_id=proposal.id,
                item_type=ItemType.DB_ROW,
                target_type=TargetType.SERIES,
                action=Action.INSERT,
                proposed_data={
                    "code": "APPLIED_SERIES_66",
                    "name": "Applied Series 66",
                    "description": "Approved series proposal materialization.",
                    "origin_type": "ingested",
                    "geography_code": geography.code,
                    "frequency": "M",
                    "temporal_stock_flow": "index",
                    "unit_kind": "index",
                    "unit_scale": "one",
                    "measure": "level",
                    "annualized": False,
                    "seasonal_adjustment": "NSA",
                    "is_active": True,
                },
                validation_status=ValidationStatus.PASSED,
            ),
            ChangeProposalItem(
                proposal_id=proposal.id,
                item_type=ItemType.DB_ROW,
                target_type=TargetType.SERIES_FAMILY_MEMBERS,
                action=Action.INSERT,
                proposed_data={
                    "family_code": family.code,
                    "series_code": "APPLIED_SERIES_66",
                    "variant": "headline",
                    "is_primary": True,
                },
                validation_status=ValidationStatus.PASSED,
            ),
        ]
    )
    await session.flush()

    result = await tools.apply_approved_proposal(
        ApplyApprovedProposalArgs(approved_proposal_id=proposal.id),
    )

    session.expire_all()
    series = (
        await session.execute(
            select(Series)
            .options(
                selectinload(Series.geography),
                selectinload(Series.family_member)
                .selectinload(SeriesFamilyMember.family)
                .selectinload(SeriesFamily.concept),
            )
            .where(Series.code == "APPLIED_SERIES_66")
        )
    ).scalar_one()
    assert result["status"] == ProposalStatus.APPLIED.value
    assert series.embedding is not None
    assert series.embedding_model == EMBEDDING_MODEL
    assert series.embedding_input_hash == hash_embedding_input(
        compose_series_embedding_input(series)
    )
    assert series.family_member is not None
    assert series.family_member.family_id == family.id


@pytest.mark.asyncio
async def test_apply_approved_proposal_rolls_back_partial_writes_when_embedding_fails(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def flaky_embed_text(text: str) -> list[float]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("embedding failure during approval")
        return [1.0] * EMBEDDING_DIMENSIONS

    monkeypatch.setattr(
        "macro_foundry.services.registration.embed_text",
        flaky_embed_text,
    )

    tools = MacrodbWriteTools(session)
    geography = (
        await session.execute(select(Geography).where(Geography.code == "HKG"))
    ).scalar_one()
    proposal = ChangeProposal(
        title="approved multi-row proposal",
        proposal_type=ProposalType.MIXED,
        status=ProposalStatus.APPROVED,
        requested_by=RequestedBy.AGENT,
        risk_level=RiskLevel.LOW,
        source_agent_session_id="sess-apply-rollback-001",
        created_by_agent="onboarding_agent",
    )
    session.add(proposal)
    await session.flush()
    session.add_all(
        [
            ChangeProposalItem(
                proposal_id=proposal.id,
                item_type=ItemType.DB_ROW,
                target_type=TargetType.CONCEPTS,
                action=Action.INSERT,
                proposed_data={
                    "code": "ROLLBACK_CONCEPT_66",
                    "name": "Rollback Concept 66",
                    "description": "Should be rolled back with the failed approval.",
                },
                validation_status=ValidationStatus.PASSED,
            ),
            ChangeProposalItem(
                proposal_id=proposal.id,
                item_type=ItemType.DB_ROW,
                target_type=TargetType.SERIES_FAMILIES,
                action=Action.INSERT,
                proposed_data={
                    "code": "ROLLBACK_FAMILY_66",
                    "name": "Rollback Family 66",
                    "description": "Should be rolled back with the failed approval.",
                    "concept_code": "ROLLBACK_CONCEPT_66",
                    "geography_code": geography.code,
                },
                validation_status=ValidationStatus.PASSED,
            ),
        ]
    )
    await session.flush()

    with pytest.raises(RuntimeError, match="embedding failure during approval"):
        await tools.apply_approved_proposal(
            ApplyApprovedProposalArgs(approved_proposal_id=proposal.id),
        )

    await session.refresh(proposal)
    assert proposal.status == ProposalStatus.APPROVED
    assert proposal.applied_at is None

    concept = (
        await session.execute(select(Concept).where(Concept.code == "ROLLBACK_CONCEPT_66"))
    ).scalar_one_or_none()
    family = (
        await session.execute(
            select(SeriesFamily).where(SeriesFamily.code == "ROLLBACK_FAMILY_66")
        )
    ).scalar_one_or_none()
    assert concept is None
    assert family is None


@pytest.mark.asyncio
async def test_mark_proposal_outcome_flips_to_applied_by_operator(
    session: AsyncSession,
) -> None:
    tools = MacrodbWriteTools(session)
    proposal = ChangeProposal(
        title="test SHA proposal",
        proposal_type=ProposalType.MIXED,
        status=ProposalStatus.PROPOSED,
        requested_by=RequestedBy.AGENT,
        risk_level=RiskLevel.LOW,
        source_agent_session_id="sess-mark-001",
        created_by_agent="onboarding_agent",
    )
    session.add(proposal)
    await session.flush()
    item = ChangeProposalItem(
        proposal_id=proposal.id,
        item_type=ItemType.DB_ROW,
        target_type=TargetType.SERIES,
        action=Action.SUGGEST_HUMAN_APPLY,
        proposed_data={"schema_field": "concept.name", "proposed_value": "CPI (renamed)"},
        validation_status=ValidationStatus.PENDING_HUMAN_APPLY,
    )
    session.add(item)
    await session.flush()

    result = await tools.mark_proposal_outcome(
        MarkProposalOutcomeArgs(
            proposal_id=item.id,
            status=ValidationStatus.APPLIED_BY_OPERATOR.value,
            applied_by="operator@test.example",
        )
    )

    assert result["validation_status"] == ValidationStatus.APPLIED_BY_OPERATOR.value

    refreshed_item = await session.get(ChangeProposalItem, item.id)
    assert refreshed_item is not None
    assert refreshed_item.validation_status == ValidationStatus.APPLIED_BY_OPERATOR

    refreshed_proposal = await session.get(ChangeProposal, proposal.id)
    assert refreshed_proposal is not None
    assert refreshed_proposal.applied_by == "operator@test.example"
    assert refreshed_proposal.applied_at is not None


# ---------------------------------------------------------------------------
# SQLAdmin mark-applied action
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_test_session_maker(
    test_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admin, "session_maker", test_session_factory)
    for view in admin.views:
        monkeypatch.setattr(view, "session_maker", test_session_factory)


@pytest.mark.asyncio
async def test_admin_mark_applied_action_flips_pending_item(
    admin_test_session_maker: None,
    session: AsyncSession,
) -> None:
    """The mark-applied admin action flips validation_status and stamps timestamps."""
    proposal = ChangeProposal(
        title="admin action test proposal",
        proposal_type=ProposalType.MIXED,
        status=ProposalStatus.PROPOSED,
        requested_by=RequestedBy.AGENT,
        risk_level=RiskLevel.LOW,
        source_agent_session_id="sess-admin-001",
        created_by_agent="onboarding_agent",
    )
    session.add(proposal)
    await session.flush()
    item = ChangeProposalItem(
        proposal_id=proposal.id,
        item_type=ItemType.DB_ROW,
        target_type=TargetType.SERIES,
        action=Action.SUGGEST_HUMAN_APPLY,
        proposed_data={"schema_field": "concept.name", "proposed_value": "CPI (admin flip)"},
        validation_status=ValidationStatus.PENDING_HUMAN_APPLY,
    )
    session.add(item)
    await session.flush()
    item_id = str(item.id)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login_response = await client.post(
            "/admin/login",
            data={
                "username": settings.admin.username,
                "password": settings.admin.password.get_secret_value(),
            },
            follow_redirects=False,
        )
        assert login_response.status_code == 302

        response = await client.get(
            f"/admin/change-proposal-item/action/mark-applied?pks={item_id}",
            follow_redirects=False,
        )
    assert response.status_code in (302, 303)

    await session.refresh(item)
    assert item.validation_status == ValidationStatus.APPLIED_BY_OPERATOR


# ---------------------------------------------------------------------------
# Integration test — AC #6
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_catalog_writes_catalog_rows_and_pending_sha_items(
    admin_test_session_maker: None,
    session: AsyncSession,
) -> None:
    """Gate 1 approval → apply_catalog → catalog rows written + SHA items pending → SQLAdmin flip."""
    draft = DraftProposal(
        concept=DraftConcept(action="new", code="TST_CONCEPT_AC6", name="Test AC6 Concept"),
        family=DraftFamily(
            action="new",
            code="TST_FAM_AC6",
            name="Test AC6 Family",
            concept_code="TST_CONCEPT_AC6",
            geography_code="HKG",
        ),
        series=DraftSeries(
            action="new",
            code="TST_SERIES_AC6",
            name="Test AC6 Series",
            frequency="M",
            measure="level",
            unit_kind="index",
            temporal_stock_flow="index",
            unit_scale="one",
            seasonal_adjustment="NSA",
        ),
        source=DraftSeriesSource(
            provider_name="HKG Census and Statistics Department",
            external_code="TST_EXT_AC6",
        ),
        feed=DraftIngestionFeed(
            selector_type="json_path",
            cron_schedule="0 9 * * *",
            feed_method="api",
        ),
        family_member=DraftFamilyMember(variant=None),
    )
    sha_item = SuggestHumanApplyItem(
        schema_field="concept.name",
        proposed_value="Test AC6 Concept (Revised)",
        rationale="test sha",
    ).model_dump(mode="json")

    state = {
        "gate_1_approved": True,
        "proposal": draft.model_dump(mode="json"),
        "suggest_human_apply": [sha_item],
        "session_metadata": {"session_id": "sess-ac6-001"},
    }

    tools = MacrodbWriteTools(session)
    node = make_apply_catalog_node(write_tools=tools)
    result = await node(state)

    assert result["gate_1_applied"] is True

    # Catalog rows written
    concept = (
        await session.execute(select(Concept).where(Concept.code == "TST_CONCEPT_AC6"))
    ).scalar_one()
    family = (
        await session.execute(select(SeriesFamily).where(SeriesFamily.code == "TST_FAM_AC6"))
    ).scalar_one()
    series = (
        await session.execute(select(Series).where(Series.code == "TST_SERIES_AC6"))
    ).scalar_one()
    assert concept.embedding is not None
    assert family.embedding is not None
    assert series.embedding is not None
    assert concept.embedding_model == EMBEDDING_MODEL
    assert family.embedding_model == EMBEDDING_MODEL
    assert series.embedding_model == EMBEDDING_MODEL
    assert series.name == "Test AC6 Series"

    feed_member = (
        await session.execute(
            select(IngestionFeedMember)
            .join(SeriesSource, IngestionFeedMember.series_source_id == SeriesSource.id)
            .where(SeriesSource.series_id == series.id)
        )
    ).scalar_one()
    assert feed_member is not None

    # SHA item recorded as PENDING_HUMAN_APPLY
    sha_items = (
        await session.execute(
            select(ChangeProposalItem).where(
                ChangeProposalItem.action == Action.SUGGEST_HUMAN_APPLY
            )
        )
    ).scalars().all()
    assert len(sha_items) == 1
    sha = sha_items[0]
    assert sha.validation_status == ValidationStatus.PENDING_HUMAN_APPLY
    sha_id = str(sha.id)

    # SQLAdmin mark-applied flips the SHA item
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login_response = await client.post(
            "/admin/login",
            data={
                "username": settings.admin.username,
                "password": settings.admin.password.get_secret_value(),
            },
            follow_redirects=False,
        )
        assert login_response.status_code == 302
        response = await client.get(
            f"/admin/change-proposal-item/action/mark-applied?pks={sha_id}",
            follow_redirects=False,
        )
    assert response.status_code in (302, 303)

    await session.refresh(sha)
    assert sha.validation_status == ValidationStatus.APPLIED_BY_OPERATOR

    sha_proposal = (
        await session.execute(select(ChangeProposal).where(ChangeProposal.id == sha.proposal_id))
    ).scalar_one()
    await session.refresh(sha_proposal)
    assert sha_proposal.applied_at is not None
