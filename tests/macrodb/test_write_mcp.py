"""Tests for write-enabled MCP tools and SQLAdmin mark-applied action (issue 47)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from macro_foundry.backend.main import admin, app
from macro_foundry.config import settings
from macro_foundry.enums import Action, ItemType, ProposalStatus, ProposalType, RequestedBy, RiskLevel, TargetType, ValidationStatus
from macro_foundry.models import ChangeProposal, ChangeProposalItem
from macro_foundry.mcp.write_tools import (
    MacrodbWriteTools,
    MarkProposalOutcomeArgs,
    ProposeCreateSeriesArgs,
    RecordSuggestHumanApplyArgs,
)


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
            payload={"series_code": "CPI_HKG_M"},
            rationale="Test",
        )
    )
    assert "proposal_id" in result
    assert "item_id" in result

    proposal = (
        await session.execute(
            select(ChangeProposal).where(
                ChangeProposal.source_agent_session_id == "sess-test-001"
            )
        )
    ).scalar_one()
    assert proposal.status == ProposalStatus.PROPOSED
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
async def test_apply_approved_proposal_validates_status(
    session: AsyncSession,
) -> None:
    tools = MacrodbWriteTools(session)
    create_result = await tools.propose_create_series(
        ProposeCreateSeriesArgs(
            session_id="sess-reject-001",
            payload={"series_code": "REJECT_TEST"},
        )
    )
    import uuid

    with pytest.raises(ValueError, match="not approved"):
        await tools.apply_approved_proposal(
            type("Args", (), {"approved_proposal_id": uuid.UUID(create_result["proposal_id"])})()
        )


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

    await session.refresh(proposal)
    assert proposal.applied_at is not None
