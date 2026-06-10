"""Tests for Gate 2 dangerous-correction path (issue 27)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Cycle 1 — Gate2Outcome enum
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_gate2_outcome_has_expected_values() -> None:
    from macro_foundry.agent.gate import Gate2Outcome

    assert Gate2Outcome.APPROVE.value == "approve"
    assert Gate2Outcome.REJECT.value == "reject"
    assert Gate2Outcome.REQUEST_CHANGES.value == "request_changes"


# ---------------------------------------------------------------------------
# Cycle 2 — DangerousCorrectionPlan model
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_dangerous_correction_plan_model_validates() -> None:
    from macro_foundry.agent.gate import DangerousCorrectionPlan

    plan = DangerousCorrectionPlan(
        collision_column="series.code",
        existing_code="CPI_HKG_ALL_M",
        proposed_code="CPI_HKG_HEADLINE_M_NSA_LEVEL",
        affected_source_mappings=["src-uuid-1"],
        affected_feeds=["feed-uuid-1"],
        affected_observations_count=142,
        affected_derivations=["DERIVED_CPI_HKG_ALL_M_YOY"],
        repair_strategy="rename_in_place",
        repair_rationale="Existing code was missing SA and measure tokens.",
    )

    assert plan.repair_strategy == "rename_in_place"
    assert plan.affected_observations_count == 142


@pytest.mark.no_db
def test_dangerous_correction_plan_requires_repair_strategy_in_allowed_set() -> None:
    import pydantic

    from macro_foundry.agent.gate import DangerousCorrectionPlan

    with pytest.raises(pydantic.ValidationError):
        DangerousCorrectionPlan(
            collision_column="series.code",
            existing_code="CPI_HKG_ALL_M",
            proposed_code="CPI_HKG_HEADLINE_M_NSA_LEVEL",
            affected_source_mappings=[],
            affected_feeds=[],
            affected_observations_count=0,
            affected_derivations=[],
            repair_strategy="delete_and_forget",  # not in allowlist
            repair_rationale="Bad idea.",
        )


# ---------------------------------------------------------------------------
# Cycle 3 — dangerous_correction_plan node produces plan from injected LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_dangerous_correction_plan_node_records_plan_in_state() -> None:
    from macro_foundry.agent.gate import make_dangerous_correction_plan_node

    plan_dict = {
        "collision_column": "series.code",
        "existing_code": "CPI_HKG_ALL_M",
        "proposed_code": "CPI_HKG_HEADLINE_M_NSA_LEVEL",
        "affected_source_mappings": ["src-1"],
        "affected_feeds": ["feed-1"],
        "affected_observations_count": 10,
        "affected_derivations": [],
        "repair_strategy": "rename_in_place",
        "repair_rationale": "Code was missing SA and measure tokens.",
    }
    planner_llm = AsyncMock(return_value={"plan": plan_dict})

    node = make_dangerous_correction_plan_node(planner_llm=planner_llm)

    state: dict[str, Any] = {
        "collision_detail": {"column": "series.code", "existing_code": "CPI_HKG_ALL_M"},
        "proposal": {"series": {"code": "CPI_HKG_HEADLINE_M_NSA_LEVEL"}},
    }
    result = await node(state)

    assert result["dangerous_correction_plan"] == plan_dict
    planner_llm.assert_called_once()


# ---------------------------------------------------------------------------
# Cycle 4 — gate_2_wait node routes on Approve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_gate_2_wait_approve_sets_gate_2_approved() -> None:
    from macro_foundry.agent.gate import Gate2Outcome, make_gate_2_wait_node

    picker = AsyncMock(return_value=Gate2Outcome.APPROVE.value)
    approval_llm = AsyncMock()

    node = make_gate_2_wait_node(picker=picker, approval_llm=approval_llm)

    plan_dict = {
        "collision_column": "series.code",
        "existing_code": "CPI_HKG_ALL_M",
        "proposed_code": "CPI_HKG_HEADLINE_M_NSA_LEVEL",
        "affected_source_mappings": [],
        "affected_feeds": [],
        "affected_observations_count": 0,
        "affected_derivations": [],
        "repair_strategy": "rename_in_place",
        "repair_rationale": "Tokens missing.",
    }
    state: dict[str, Any] = {"dangerous_correction_plan": plan_dict}
    result = await node(state)

    assert result["gate_2_approved"] is True
    assert result["gate_2_outcome"] == Gate2Outcome.APPROVE.value
    approval_llm.assert_not_called()


# ---------------------------------------------------------------------------
# Cycle 5 — gate_2_wait node routes on Reject (no LLM call)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_gate_2_wait_reject_does_not_set_approved() -> None:
    from macro_foundry.agent.gate import Gate2Outcome, make_gate_2_wait_node

    picker = AsyncMock(return_value=Gate2Outcome.REJECT.value)
    approval_llm = AsyncMock()

    node = make_gate_2_wait_node(picker=picker, approval_llm=approval_llm)

    state: dict[str, Any] = {"dangerous_correction_plan": {}}
    result = await node(state)

    assert result.get("gate_2_approved") is not True
    assert result["gate_2_outcome"] == Gate2Outcome.REJECT.value
    approval_llm.assert_not_called()


# ---------------------------------------------------------------------------
# Cycle 6 — dangerous_correction_executor applies repair and records result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_dangerous_correction_executor_applies_repair_and_records_result() -> None:
    from macro_foundry.agent.gate import make_dangerous_correction_executor_node

    repair_fn = AsyncMock(return_value={"renamed_series_id": "uuid-abc", "affected_rows": 10})
    node = make_dangerous_correction_executor_node(repair_fn=repair_fn)

    plan_dict = {
        "collision_column": "series.code",
        "existing_code": "CPI_HKG_ALL_M",
        "proposed_code": "CPI_HKG_HEADLINE_M_NSA_LEVEL",
        "affected_source_mappings": ["src-1"],
        "affected_feeds": ["feed-1"],
        "affected_observations_count": 10,
        "affected_derivations": [],
        "repair_strategy": "rename_in_place",
        "repair_rationale": "Tokens missing.",
    }
    state: dict[str, Any] = {
        "dangerous_correction_plan": plan_dict,
        "gate_2_approved": True,
    }
    result = await node(state)

    assert result["dangerous_correction_repair"]["renamed_series_id"] == "uuid-abc"
    repair_fn.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_dangerous_correction_executor_rejects_when_not_gate_2_approved() -> None:
    from macro_foundry.agent.gate import make_dangerous_correction_executor_node

    repair_fn = AsyncMock(return_value={})
    node = make_dangerous_correction_executor_node(repair_fn=repair_fn)

    state: dict[str, Any] = {
        "dangerous_correction_plan": {"repair_strategy": "rename_in_place"},
        "gate_2_approved": False,
    }
    result = await node(state)

    repair_fn.assert_not_called()
    assert not result.get("dangerous_correction_repair")


# ---------------------------------------------------------------------------
# Shared helpers for graph-level tests
# ---------------------------------------------------------------------------

_DRAFT_PAYLOAD = {
    "concept": {"action": "new", "code": "CPI", "name": "Consumer Price Index"},
    "family": {"action": "new", "code": "HKG_CPI", "name": "Hong Kong CPI", "geography_code": "HKG"},
    "series": {
        "action": "new",
        "code": "CPI_HKG_ALL_M",
        "name": "HKG CPI Headline",
        "description": "HKG Consumer Price Index, headline NSA.",
        "frequency": "M",
        "seasonal_adjustment": "NSA",
        "measure": "LEVEL",
        "temporal_stock_flow": "FLOW",
        "unit_scale": "ONE",
        "unit_kind": "INDEX",
    },
    "family_member": {"variant": "Headline"},
    "sources": [],
    "feed": {"feed_method": "api", "selector_type": "json_path", "selector_config": {}},
}

_LLM_USAGE = {
    "prompt_tokens": 10,
    "completion_tokens": 5,
    "total_tokens": 15,
    "cost_estimate_usd": 0.0001,
    "latency_ms": 50,
}

_REVIEWER_RETURN = {
    "findings": [],
    "bounce_to_drafter": False,
    **_LLM_USAGE,
}


async def _research_llm_stub(_messages: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "source_summary": "CPI data available from HKG CenStatD.",
        "existing_catalog_hits": [],
        "ambiguity_flags": [],
        "credential_gap_proposals": [],
        **_LLM_USAGE,
    }


async def _empty_cohorts(_catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
    return {"cohort_a": [], "cohort_b": [], "cohort_c": []}


async def _config_only(_source_summary: str) -> str:
    return "config_only"


async def _reviewer_llm_stub(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return _REVIEWER_RETURN


class _MemoryChannel:
    async def emit(self, event: Any) -> None:
        pass

    async def prompt(self, prompt: Any) -> Any:
        from macro_foundry.agent.channel import ChannelResponse
        return ChannelResponse(text="")


def _build_graph(
    *,
    gate_1_picker: Any,
    approval_llm: Any,
    unique_checker: Any,
    collision_picker: Any,
    draft_llm: Any,
    gate_2_picker: Any = None,
    planner_llm: Any = None,
    repair_fn: Any = None,
    thread_id: str,
) -> Any:
    from langgraph.checkpoint.memory import MemorySaver

    from macro_foundry.agent.graph import build_onboarding_graph
    from macro_foundry.agent.roles import default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    return build_onboarding_graph(
        checkpointer=MemorySaver(),
        research_llm=_research_llm_stub,
        cohort_lookup=_empty_cohorts,
        extraction_mode_classifier=_config_only,
        draft_llm=draft_llm,
        governance_llm=_reviewer_llm_stub,
        data_correctness_llm=_reviewer_llm_stub,
        gate_1_picker=gate_1_picker,
        approval_llm=approval_llm,
        channel=_MemoryChannel(),
        write_tools=AsyncMock(),
        run_logs=AsyncMock(),
        test_reviewer=AsyncMock(return_value={"summary": "ok"}),
        package_store=AsyncMock(return_value={"package_id": "pkg-1"}),
        role_configs=default_role_configs(),
        registry=SkillRegistry({}),
        unique_checker=unique_checker,
        collision_picker=collision_picker,
        gate_2_picker=gate_2_picker,
        planner_llm=planner_llm,
        repair_fn=repair_fn,
    )


def _initial_state(session_id: str) -> dict[str, Any]:
    from datetime import datetime, timezone

    from macro_foundry.agent.onboarding_state import SessionMetadata

    return {
        "pending_input": "Onboard HKG CPI",
        "session_metadata": SessionMetadata(
            session_id=session_id,
            target_environment="dev",
            created_at=datetime.now(timezone.utc),
            created_by="tester",
            cli_version="0.0.0",
        ).model_dump(mode="json"),
    }


def _draft_llm_stub(proposal_dict: dict[str, Any]) -> Any:
    """Return an async stub that always returns the given proposal."""
    async def _stub(_messages: list[dict[str, str]]) -> dict[str, Any]:
        return {"proposal": proposal_dict, "enum_gap_proposals": [], "harmonisation_items": [], "suggest_human_apply": [], **_LLM_USAGE}
    return _stub


# ---------------------------------------------------------------------------
# Cycle 7 — graph-level: small-edit happy path (no collision → loop back → reject)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_graph_small_edit_happy_path_no_collision() -> None:
    """No collision: apply_small_edit loops back to gate_1_wait and gate is re-issued.

    Using REJECT on the second pick avoids needing a full write_tools stub while
    still proving that gate_1_wait was invoked a second time after the edit.
    """
    from macro_foundry.agent.gate import GateOutcome

    gate_1_picker_calls: list[str] = []

    async def _gate_1_picker(options: list[str], *_args: Any) -> str:
        gate_1_picker_calls.append("called")
        if len(gate_1_picker_calls) == 1:
            return GateOutcome.REQUEST_CHANGES.value
        return GateOutcome.REJECT.value

    unique_checker = AsyncMock(return_value=None)  # no collision

    graph = _build_graph(
        gate_1_picker=_gate_1_picker,
        approval_llm=AsyncMock(return_value={"edit_instructions": "rename series.code to CPI_HKG_ALL_M_NSA_LEVEL"}),
        unique_checker=unique_checker,
        collision_picker=None,
        draft_llm=_draft_llm_stub(_DRAFT_PAYLOAD),
        thread_id="test-small-edit-happy",
    )

    final_state = await graph.ainvoke(
        _initial_state("s-happy"),
        config={"configurable": {"thread_id": "test-small-edit-happy"}},
    )

    # Gate 1 was called twice — REQUEST_CHANGES then REJECT — proving the loop worked.
    assert len(gate_1_picker_calls) == 2
    # No dangerous-correction path was triggered.
    assert not final_state.get("gate_2_approved")
    unique_checker.assert_called()


# ---------------------------------------------------------------------------
# Cycle 8 — graph-level: collision → all three operator choices route correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
@pytest.mark.parametrize(
    "collision_choice",
    ["rename", "cancel", "challenge_existing"],
)
async def test_graph_collision_paths_route_correctly(collision_choice: str) -> None:
    """Each collision choice routes the graph to the correct terminal.

    rename / cancel  → back to gate_1_wait (REJECT terminates cleanly, no dangerous path)
    challenge_existing → dangerous_correction_plan → gate_2_wait → executor
    """
    from macro_foundry.agent.gate import Gate2Outcome, GateOutcome

    collision_detail = {"column": "series.code", "existing_code": "CPI_HKG_ALL_M"}
    gate_1_calls: list[int] = []

    async def _gate_1_picker(options: list[str], *_: Any) -> str:
        gate_1_calls.append(1)
        if len(gate_1_calls) == 1:
            return GateOutcome.REQUEST_CHANGES.value
        return GateOutcome.REJECT.value

    async def _gate_2_picker(options: list[str], *_: Any) -> str:
        return Gate2Outcome.APPROVE.value

    plan_dict = {
        "collision_column": "series.code",
        "existing_code": "CPI_HKG_ALL_M",
        "proposed_code": "CPI_HKG_ALL_M_NSA_LEVEL",
        "affected_source_mappings": [],
        "affected_feeds": [],
        "affected_observations_count": 0,
        "affected_derivations": [],
        "repair_strategy": "rename_in_place",
        "repair_rationale": "Tokens missing.",
    }
    planner_llm = AsyncMock(return_value={"plan": plan_dict})
    repair_fn = AsyncMock(return_value={"renamed_series_id": "uuid-abc"})

    graph = _build_graph(
        gate_1_picker=_gate_1_picker,
        approval_llm=AsyncMock(return_value={"edit_instructions": "rename series.code to NEW_CODE"}),
        unique_checker=AsyncMock(return_value=collision_detail),
        collision_picker=AsyncMock(return_value=collision_choice),
        draft_llm=_draft_llm_stub(_DRAFT_PAYLOAD),
        gate_2_picker=_gate_2_picker,
        planner_llm=planner_llm,
        repair_fn=repair_fn,
        thread_id=f"test-collision-{collision_choice}",
    )

    final_state = await graph.ainvoke(
        _initial_state(f"s-coll-{collision_choice}"),
        config={"configurable": {"thread_id": f"test-collision-{collision_choice}"}},
    )

    if collision_choice == "challenge_existing":
        # Must have gone to dangerous_correction_plan → gate_2_wait → executor.
        assert final_state.get("gate_2_approved") is True
        planner_llm.assert_called_once()
        repair_fn.assert_called_once()
    else:
        # rename / cancel both loop back to gate_1_wait then terminate via REJECT.
        assert not final_state.get("gate_2_approved")
        # Gate 1 was called twice.
        assert len(gate_1_calls) == 2


# ---------------------------------------------------------------------------
# Cycle 9 — graph-level: full dangerous-correction session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_graph_dangerous_correction_full_session() -> None:
    """Full dangerous-correction session: collision → plan → Gate 2 approve → repair executed."""
    from macro_foundry.agent.gate import Gate2Outcome, GateOutcome

    collision_detail = {"column": "series.code", "existing_code": "CPI_HKG_ALL_M"}

    async def _gate_1_picker(options: list[str], *_: Any) -> str:
        return GateOutcome.REQUEST_CHANGES.value

    async def _gate_2_picker(options: list[str], *_: Any) -> str:
        return Gate2Outcome.APPROVE.value

    plan_dict = {
        "collision_column": "series.code",
        "existing_code": "CPI_HKG_ALL_M",
        "proposed_code": "CPI_HKG_ALL_M_NSA_LEVEL",
        "affected_source_mappings": ["src-1"],
        "affected_feeds": ["feed-1"],
        "affected_observations_count": 99,
        "affected_derivations": ["YOY_CPI"],
        "repair_strategy": "rename_in_place",
        "repair_rationale": "Original code missing SA and measure tokens.",
    }
    planner_llm = AsyncMock(return_value={"plan": plan_dict})
    repair_fn = AsyncMock(return_value={"renamed_series_id": "uuid-xyz", "affected_rows": 99})

    graph = _build_graph(
        gate_1_picker=_gate_1_picker,
        approval_llm=AsyncMock(return_value={"edit_instructions": "rename series.code to CPI_HKG_ALL_M_NSA_LEVEL"}),
        unique_checker=AsyncMock(return_value=collision_detail),
        collision_picker=AsyncMock(return_value="challenge_existing"),
        draft_llm=_draft_llm_stub(_DRAFT_PAYLOAD),
        gate_2_picker=_gate_2_picker,
        planner_llm=planner_llm,
        repair_fn=repair_fn,
        thread_id="test-full-dc",
    )

    final_state = await graph.ainvoke(
        _initial_state("s-dc"),
        config={"configurable": {"thread_id": "test-full-dc"}},
    )

    assert final_state.get("gate_2_approved") is True
    assert final_state.get("dangerous_correction_repair", {}).get("renamed_series_id") == "uuid-xyz"
    planner_llm.assert_called_once()
    repair_fn.assert_called_once()
