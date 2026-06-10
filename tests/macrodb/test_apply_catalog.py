"""Tests for apply_catalog node (issue 47)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

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


def _base_state(**overrides: Any) -> dict[str, Any]:
    proposal = DraftProposal(
        concept=DraftConcept(action="new", code="CPI", name="Consumer Price Index"),
        family=DraftFamily(
            action="new",
            code="CPI_HKG",
            name="CPI Hong Kong",
            concept_code="CPI",
            geography_code="HKG",
        ),
        series=DraftSeries(
            action="new",
            code="CPI_HKG_TOTAL_M",
            name="CPI Hong Kong Total Monthly",
            frequency="M",
            measure="level",
            unit_kind="index",
            temporal_stock_flow="index",
            unit_scale="one",
            seasonal_adjustment="NSA",
        ),
        source=DraftSeriesSource(
            provider_name="HKG Census and Statistics Department",
            external_code="CPI_HKG_001",
        ),
        feed=DraftIngestionFeed(
            selector_type="json_path",
            cron_schedule="0 9 * * *",
            feed_method="api",
        ),
        family_member=DraftFamilyMember(variant=None),
    )
    state: dict[str, Any] = {
        "gate_1_approved": True,
        "gate_1_applied": False,
        "proposal": proposal.model_dump(mode="json"),
        "harmonisation_items": [],
        "suggest_human_apply_items": [],
        "session_metadata": {"session_id": "sess-abc"},
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_apply_catalog_refuses_when_not_approved() -> None:
    write_tools = AsyncMock()
    node = make_apply_catalog_node(write_tools=write_tools)

    state = _base_state(gate_1_approved=False)
    with pytest.raises(RuntimeError, match="gate_1_approved"):
        await node(state)

    write_tools.propose_create_series.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_apply_catalog_sets_gate_1_applied() -> None:
    write_tools = AsyncMock()
    write_tools.propose_create_series.return_value = {
        "proposal_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "item_id": "aaaaaaaa-0000-0000-0000-000000000002",
    }

    node = make_apply_catalog_node(write_tools=write_tools)
    result = await node(_base_state())

    assert result.get("gate_1_applied") is True


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_apply_catalog_calls_propose_create_series() -> None:
    write_tools = AsyncMock()
    write_tools.propose_create_series.return_value = {
        "proposal_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "item_id": "aaaaaaaa-0000-0000-0000-000000000002",
    }

    node = make_apply_catalog_node(write_tools=write_tools)
    await node(_base_state())

    write_tools.propose_create_series.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_apply_catalog_applies_credential_gap_resolutions_after_gate_1() -> None:
    write_tools = AsyncMock()
    write_tools.propose_create_series.return_value = {
        "proposal_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "item_id": "aaaaaaaa-0000-0000-0000-000000000002",
    }
    credential_resolutions = [
        {
            "outcome": "provisioned",
            "provider_identity": {
                "kind": "new",
                "proposed_provider_name": "Example Provider",
            },
            "applied_env_var_name": "EXAMPLE_API_KEY",
            "applied_auth_scheme": "bearer_header",
            "applied_rate_limit_config": {"requests_per_minute": 60},
        }
    ]

    node = make_apply_catalog_node(write_tools=write_tools)
    await node(_base_state(credential_gap_resolutions=credential_resolutions))

    write_tools.apply_credential_gap_resolutions.assert_called_once()
    args = write_tools.apply_credential_gap_resolutions.call_args.args[0]
    assert args.resolutions == credential_resolutions


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_apply_catalog_skips_suggest_human_apply_items() -> None:
    write_tools = AsyncMock()
    write_tools.propose_create_series.return_value = {
        "proposal_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "item_id": "aaaaaaaa-0000-0000-0000-000000000002",
    }
    write_tools.record_suggest_human_apply.return_value = {
        "proposal_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "item_ids": ["aaaaaaaa-0000-0000-0000-000000000003"],
    }

    sha_items = [
        SuggestHumanApplyItem(
            schema_field="concept.name",
            proposed_value="Consumer Price Index (Revised)",
            rationale="More specific",
        ).model_dump(mode="json"),
    ]

    node = make_apply_catalog_node(write_tools=write_tools)
    result = await node(_base_state(suggest_human_apply_items=sha_items))

    # Suggest-human-apply items must be recorded but NOT applied
    write_tools.record_suggest_human_apply.assert_called_once()
    call_args = write_tools.record_suggest_human_apply.call_args[0][0]
    assert len(call_args.items) == 1
    assert result.get("gate_1_applied") is True


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_apply_catalog_skips_suggest_human_apply_without_regular_items() -> None:
    """With only suggest_human_apply items and no catalog write, gate_1_applied is still True."""
    write_tools = AsyncMock()
    write_tools.propose_create_series.return_value = {
        "proposal_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "item_id": "aaaaaaaa-0000-0000-0000-000000000002",
    }
    write_tools.record_suggest_human_apply.return_value = {
        "proposal_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "item_ids": ["aaaaaaaa-0000-0000-0000-000000000003"],
    }

    sha_items = [
        {"schema_field": "concept.name", "proposed_value": "CPI (alt)", "rationale": "test"},
    ]

    node = make_apply_catalog_node(write_tools=write_tools)
    result = await node(_base_state(suggest_human_apply_items=sha_items))

    assert result.get("gate_1_applied") is True


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_apply_catalog_records_node_transition() -> None:
    write_tools = AsyncMock()
    write_tools.propose_create_series.return_value = {
        "proposal_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "item_id": "aaaaaaaa-0000-0000-0000-000000000002",
    }

    node = make_apply_catalog_node(write_tools=write_tools)
    result = await node(_base_state())

    transitions = result.get("node_transitions", [])
    assert len(transitions) == 1
    assert transitions[0]["node"] == "apply_catalog"
    assert transitions[0]["event"] == "completed"
