"""Tests for Gate 1 wait node, approval_parse, apply_small_edit, un-approval (issue 45)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Cycle 1 — GateOutcome + CollisionChoice enums
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_gate_outcome_has_expected_values() -> None:
    from macro_foundry.agent.gate import GateOutcome

    assert GateOutcome.APPROVE.value == "approve"
    assert GateOutcome.REJECT.value == "reject"
    assert GateOutcome.REQUEST_CHANGES.value == "request_changes"
    assert GateOutcome.PERMIT_FURTHER_CYCLE.value == "permit_further_cycle"


@pytest.mark.no_db
def test_collision_choice_has_expected_values() -> None:
    from macro_foundry.agent.gate import CollisionChoice

    assert CollisionChoice.RENAME.value == "rename"
    assert CollisionChoice.CHALLENGE_EXISTING.value == "challenge_existing"
    assert CollisionChoice.CANCEL.value == "cancel"


# ---------------------------------------------------------------------------
# Cycle 2 — gate_1_wait renders three-section summary
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_gate_1_summary_contains_three_section_headings() -> None:
    from macro_foundry.agent.gate import render_gate_1_summary
    from macro_foundry.agent.proposal import (
        DraftConcept,
        DraftFamily,
        DraftFamilyMember,
        DraftIngestionFeed,
        DraftProposal,
        DraftSeries,
        DraftSeriesSource,
    )

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
            code="CPI_HKG_M",
            name="CPI Hong Kong Monthly",
            frequency="M",
            measure="level",
            unit_kind="index",
            temporal_stock_flow="index",
            unit_scale="one",
            seasonal_adjustment="NSA",
        ),
        source=DraftSeriesSource(
            provider_name="HKG Census and Statistics Department",
            external_code="A",
            external_name="CPI All Items",
        ),
        feed=DraftIngestionFeed(
            selector_type="censtatd_json",
            cron_schedule="0 9 * * 1",
            feed_method="api",
        ),
        family_member=DraftFamilyMember(),
    )
    harmonisation_items: list[dict[str, Any]] = [
        {"field": "description", "series_code": "CPI_USA_M", "proposed": "Updated description."},
    ]
    suggest_human_apply: list[dict[str, Any]] = [
        {"field": "concept.name", "proposed": "Consumer Prices"},
    ]

    summary = render_gate_1_summary(
        proposal=proposal,
        harmonisation_items=harmonisation_items,
        suggest_human_apply=suggest_human_apply,
    )

    assert "New series items" in summary
    assert "Harmonisation companion items" in summary
    assert "Suggest-for-human-apply items" in summary


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _minimal_proposal() -> Any:
    from macro_foundry.agent.proposal import (
        DraftConcept,
        DraftFamily,
        DraftFamilyMember,
        DraftIngestionFeed,
        DraftProposal,
        DraftSeries,
        DraftSeriesSource,
    )

    return DraftProposal(
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
            code="CPI_HKG_M",
            name="CPI Hong Kong Monthly",
            frequency="M",
            measure="level",
            unit_kind="index",
            temporal_stock_flow="index",
            unit_scale="one",
            seasonal_adjustment="NSA",
        ),
        source=DraftSeriesSource(
            provider_name="HKG Census and Statistics Department",
            external_code="A",
        ),
        feed=DraftIngestionFeed(
            selector_type="censtatd_json",
            cron_schedule="0 9 * * 1",
            feed_method="api",
        ),
        family_member=DraftFamilyMember(),
    )


def _fake_channel() -> Any:
    """Channel stub that records emitted text and ignores prompts."""
    channel = MagicMock()
    channel.emit = AsyncMock()
    channel.prompt = AsyncMock()
    return channel


def _fake_picker(outcome: str) -> Any:
    """Picker stub that always returns the given outcome string."""
    return AsyncMock(return_value=outcome)


# ---------------------------------------------------------------------------
# Cycle 3 — Approve at cycle ≤ 2 sets gate_1_approved, no LLM
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_approve_at_cycle_1_sets_approved_flag_no_llm() -> None:
    from macro_foundry.agent.gate import GateOutcome, make_gate_1_wait_node
    from macro_foundry.agent.graph import OnboardingGraphState

    llm = AsyncMock()  # must NOT be called on Approve
    channel = _fake_channel()
    picker = _fake_picker(GateOutcome.APPROVE.value)

    node = make_gate_1_wait_node(channel=channel, approval_llm=llm, picker=picker)

    state: OnboardingGraphState = {
        "proposal": _minimal_proposal().model_dump(mode="json"),
        "review_cycle": 1,
    }
    result = await node(state)

    assert result.get("gate_1_outcome") == GateOutcome.APPROVE.value
    assert result.get("gate_1_approved") is True
    llm.assert_not_called()


# ---------------------------------------------------------------------------
# Cycle 4 — Reject sets outcome, no LLM, no approved flag
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_reject_sets_outcome_no_llm_no_approved_flag() -> None:
    from macro_foundry.agent.gate import GateOutcome, make_gate_1_wait_node
    from macro_foundry.agent.graph import OnboardingGraphState

    llm = AsyncMock()
    channel = _fake_channel()
    picker = _fake_picker(GateOutcome.REJECT.value)

    node = make_gate_1_wait_node(channel=channel, approval_llm=llm, picker=picker)

    state: OnboardingGraphState = {
        "proposal": _minimal_proposal().model_dump(mode="json"),
        "review_cycle": 1,
    }
    result = await node(state)

    assert result.get("gate_1_outcome") == GateOutcome.REJECT.value
    assert "gate_1_approved" not in result
    llm.assert_not_called()


# ---------------------------------------------------------------------------
# Cycle 5 — Request changes calls approval_llm and sets small_edit_instructions
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_request_changes_calls_llm_and_sets_edit_instructions() -> None:
    from macro_foundry.agent.gate import GateOutcome, make_gate_1_wait_node
    from macro_foundry.agent.graph import OnboardingGraphState

    llm = AsyncMock(return_value={"edit_instructions": "rename series code to CPI_HKG_ALL_M"})
    channel = _fake_channel()
    picker = _fake_picker(GateOutcome.REQUEST_CHANGES.value)

    node = make_gate_1_wait_node(channel=channel, approval_llm=llm, picker=picker)

    state: OnboardingGraphState = {
        "proposal": _minimal_proposal().model_dump(mode="json"),
        "review_cycle": 1,
    }
    result = await node(state)

    assert result.get("gate_1_outcome") == GateOutcome.REQUEST_CHANGES.value
    assert result.get("small_edit_instructions") == "rename series code to CPI_HKG_ALL_M"
    llm.assert_called_once()


# ---------------------------------------------------------------------------
# Cycle 6 — Cycle-3 picker offers permit_further_cycle, not request_changes
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_cycle_3_picker_options_include_permit_further_cycle() -> None:
    from macro_foundry.agent.gate import GateOutcome, _normal_picker_options

    options = _normal_picker_options(review_cycle=3)

    assert GateOutcome.PERMIT_FURTHER_CYCLE.value in options
    assert GateOutcome.REQUEST_CHANGES.value not in options


@pytest.mark.no_db
def test_cycle_1_picker_options_include_request_changes_not_permit() -> None:
    from macro_foundry.agent.gate import GateOutcome, _normal_picker_options

    options = _normal_picker_options(review_cycle=1)

    assert GateOutcome.REQUEST_CHANGES.value in options
    assert GateOutcome.PERMIT_FURTHER_CYCLE.value not in options


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_cycle_3_approve_sets_flag() -> None:
    from macro_foundry.agent.gate import GateOutcome, make_gate_1_wait_node
    from macro_foundry.agent.graph import OnboardingGraphState

    llm = AsyncMock()
    channel = _fake_channel()
    picker = _fake_picker(GateOutcome.APPROVE.value)

    node = make_gate_1_wait_node(channel=channel, approval_llm=llm, picker=picker)

    state: OnboardingGraphState = {
        "proposal": _minimal_proposal().model_dump(mode="json"),
        "review_cycle": 3,
    }
    result = await node(state)

    assert result.get("gate_1_approved") is True
    llm.assert_not_called()


# ---------------------------------------------------------------------------
# Cycle 7 — apply_small_edit no-collision path
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_apply_small_edit_no_collision_clears_outcome_and_updates_proposal() -> None:
    from macro_foundry.agent.gate import make_apply_small_edit_node
    from macro_foundry.agent.graph import OnboardingGraphState

    # Uniqueness checker returns no collision
    unique_checker = AsyncMock(return_value=None)

    node = make_apply_small_edit_node(unique_checker=unique_checker)

    proposal = _minimal_proposal()
    state: OnboardingGraphState = {
        "proposal": proposal.model_dump(mode="json"),
        "small_edit_instructions": "rename series code to CPI_HKG_ALL_M",
        "gate_1_outcome": "request_changes",
    }
    result = await node(state)

    # gate_1_outcome cleared so gate_1_wait will re-issue the picker
    assert result.get("gate_1_outcome") is None
    # proposal updated in-memory
    assert result.get("proposal") is not None
    assert result.get("small_edit_instructions") is None


# ---------------------------------------------------------------------------
# Cycle 8 — apply_small_edit collision path renders three-way choice
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_apply_small_edit_collision_sets_collision_choice_and_detail() -> None:
    from macro_foundry.agent.gate import CollisionChoice, make_apply_small_edit_node
    from macro_foundry.agent.graph import OnboardingGraphState

    collision_detail = {"column": "series.code", "existing_code": "CPI_HKG_ALL_M"}
    unique_checker = AsyncMock(return_value=collision_detail)
    collision_picker = AsyncMock(return_value=CollisionChoice.RENAME.value)

    node = make_apply_small_edit_node(
        unique_checker=unique_checker,
        collision_picker=collision_picker,
    )

    state: OnboardingGraphState = {
        "proposal": _minimal_proposal().model_dump(mode="json"),
        "small_edit_instructions": "rename series code to CPI_HKG_ALL_M",
    }
    result = await node(state)

    assert result.get("collision_choice") == CollisionChoice.RENAME.value
    assert result.get("collision_detail") == collision_detail
    collision_picker.assert_called_once()


# ---------------------------------------------------------------------------
# Cycle 9 — challenge_existing sets gate_2_escalation flag
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_challenge_existing_sets_gate_2_escalation_flag() -> None:
    from macro_foundry.agent.gate import CollisionChoice, make_apply_small_edit_node
    from macro_foundry.agent.graph import OnboardingGraphState

    collision_detail = {"column": "series.code", "existing_code": "CPI_HKG_ALL_M"}
    unique_checker = AsyncMock(return_value=collision_detail)
    collision_picker = AsyncMock(return_value=CollisionChoice.CHALLENGE_EXISTING.value)

    node = make_apply_small_edit_node(
        unique_checker=unique_checker,
        collision_picker=collision_picker,
    )

    state: OnboardingGraphState = {
        "proposal": _minimal_proposal().model_dump(mode="json"),
        "small_edit_instructions": "rename series code to CPI_HKG_ALL_M",
    }
    result = await node(state)

    assert result.get("collision_choice") == CollisionChoice.CHALLENGE_EXISTING.value
    assert result.get("gate_2_escalation") is True


# ---------------------------------------------------------------------------
# Cycle 10 — Un-approval window: unapprove before apply_catalog rolls back flag
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_unapprove_before_apply_catalog_resets_approved_flag() -> None:
    from macro_foundry.agent.gate import make_unapprove_node
    from macro_foundry.agent.graph import OnboardingGraphState

    node = make_unapprove_node()

    state: OnboardingGraphState = {
        "gate_1_approved": True,
        "gate_1_applied": False,
        "gate_1_outcome": "approve",
    }
    result = await node(state)

    assert result.get("gate_1_approved") is False
    assert result.get("gate_1_outcome") is None


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_unapprove_after_apply_catalog_is_rejected() -> None:
    from macro_foundry.agent.gate import make_unapprove_node
    from macro_foundry.agent.graph import OnboardingGraphState

    node = make_unapprove_node()

    state: OnboardingGraphState = {
        "gate_1_approved": True,
        "gate_1_applied": True,  # already written
        "gate_1_outcome": "approve",
    }
    result = await node(state)

    # Post-apply revocation is not allowed; flag must not be cleared
    assert result.get("gate_1_approved") is True
    assert result.get("unapprove_rejected") is True


# ---------------------------------------------------------------------------
# Cycle 11 — Structural edits route back through drafter cycle, not small-edit
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_is_structural_edit_returns_true_for_methodology_changes() -> None:
    from macro_foundry.agent.gate import is_structural_edit

    assert is_structural_edit("change frequency to quarterly") is True
    assert is_structural_edit("update the methodology description") is True
    assert is_structural_edit("change hierarchy edge parent to GDP_HKG_Q") is True
    assert is_structural_edit("update selector configuration") is True


@pytest.mark.no_db
def test_is_structural_edit_returns_false_for_textual_edits() -> None:
    from macro_foundry.agent.gate import is_structural_edit

    assert is_structural_edit("rename series code to CPI_HKG_ALL_M") is False
    assert is_structural_edit("update the description to clarify scope") is False
    assert is_structural_edit("change the name to something clearer") is False
