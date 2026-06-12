"""Tests for governance_review and data_correctness_review nodes (issue 44)."""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Slice 1 — ReviewBundle model
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_review_bundle_constructs_with_required_fields() -> None:
    from macro_foundry.agent.review import ReviewBundle

    bundle = ReviewBundle(
        specialty="governance",
        findings=["Schema fit is acceptable.", "Provider locator is weak."],
        review_cycle=1,
        bounce_to_drafter=False,
    )
    assert bundle.specialty == "governance"
    assert len(bundle.findings) == 2
    assert bundle.review_cycle == 1
    assert bundle.bounce_to_drafter is False


@pytest.mark.no_db
def test_review_bundle_data_correctness_specialty() -> None:
    from macro_foundry.agent.review import ReviewBundle

    bundle = ReviewBundle(
        specialty="data_correctness",
        findings=["Magnitude band looks correct."],
        review_cycle=2,
        bounce_to_drafter=True,
    )
    assert bundle.specialty == "data_correctness"
    assert bundle.bounce_to_drafter is True


@pytest.mark.no_db
def test_review_bundle_rejects_unknown_specialty() -> None:
    from pydantic import ValidationError

    from macro_foundry.agent.review import ReviewBundle

    with pytest.raises(ValidationError):
        ReviewBundle(
            specialty="selector",
            findings=[],
            review_cycle=1,
            bounce_to_drafter=False,
        )


# ---------------------------------------------------------------------------
# Slice 2 — State fields: review_cycle, governance_review, data_correctness_review
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_onboarding_graph_state_accepts_review_fields() -> None:
    from macro_foundry.agent.graph import OnboardingGraphState
    from macro_foundry.agent.review import ReviewBundle

    bundle = ReviewBundle(
        specialty="governance",
        findings=["OK"],
        review_cycle=1,
        bounce_to_drafter=False,
    )
    # TypedDict — just verify the keys are accepted without KeyError
    state: OnboardingGraphState = {
        "review_cycle": 1,
        "governance_review": bundle.model_dump(mode="json"),
        "data_correctness_review": None,
    }  # type: ignore[typeddict-item]
    assert state["review_cycle"] == 1
    assert state["governance_review"] is not None


@pytest.mark.no_db
def test_checkpoint_state_accepts_review_bundles() -> None:
    from datetime import datetime, timezone

    from macro_foundry.agent.onboarding_state import OnboardingCheckpointState, SessionMetadata
    from macro_foundry.agent.review import ReviewBundle
    from macro_foundry.db import EnvTarget

    gov = ReviewBundle(
        specialty="governance",
        findings=["Schema OK"],
        review_cycle=1,
        bounce_to_drafter=False,
    )
    dc = ReviewBundle(
        specialty="data_correctness",
        findings=["Magnitude OK"],
        review_cycle=1,
        bounce_to_drafter=False,
    )
    state = OnboardingCheckpointState(
        session_metadata=SessionMetadata(
            session_id="s1",
            target_environment=EnvTarget.DEV.value,
            created_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
            created_by="macrodb-cli",
            cli_version="0.1.0",
        ),
        governance_review=gov,
        data_correctness_review=dc,
        review_cycle=1,
    )
    assert state.governance_review is not None
    assert state.data_correctness_review is not None
    assert state.review_cycle == 1


# ---------------------------------------------------------------------------
# Slice 3 — governance_review node: writes ReviewBundle + LLM call
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_governance_review_node_writes_review_bundle() -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.review import ReviewBundle
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        return {
            "findings": ["Schema fit OK.", "Provider locator acceptable."],
            "bounce_to_drafter": False,
            "prompt_tokens": 150,
            "completion_tokens": 80,
            "total_tokens": 230,
            "cost_estimate_usd": 0.002,
            "latency_ms": 300,
        }

    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(fake_llm, role_config, registry)

    state = {
        "proposal": {"concept": {"code": "CPI"}},
        "extraction_mode": "config_only",
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    }

    result = await node(state)

    assert result["governance_review"] is not None
    bundle = ReviewBundle.model_validate(result["governance_review"])
    assert bundle.specialty == "governance"
    assert bundle.bounce_to_drafter is False
    assert bundle.review_cycle == 1


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_governance_review_node_records_llm_call() -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        return {
            "findings": ["OK"],
            "bounce_to_drafter": False,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(fake_llm, role_config, registry)

    result = await node({
        "proposal": {},
        "extraction_mode": "config_only",
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert len(result["llm_calls"]) == 1
    call = result["llm_calls"][0]
    assert call["role"] == "governance_reviewer"
    assert call["total_tokens"] == 150


# ---------------------------------------------------------------------------
# Slice 4 — Conditional selector skill + task_hint for custom_python
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_governance_review_sets_task_hint_selector_code_review_when_custom_python() -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})
    captured_task_hints: list[str | None] = []

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        captured_task_hints.append(task_hint)
        return {
            "findings": ["Selector code looks OK."],
            "bounce_to_drafter": False,
            "prompt_tokens": 200,
            "completion_tokens": 100,
            "total_tokens": 300,
            "cost_estimate_usd": 0.003,
            "latency_ms": 400,
        }

    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(fake_llm, role_config, registry)

    await node({
        "proposal": {"proposed_scripts": ["import requests"]},
        "extraction_mode": "custom_python",
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert captured_task_hints == ["selector_code_review"]


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_governance_review_does_not_set_task_hint_when_config_only() -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})
    captured_task_hints: list[str | None] = []

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        captured_task_hints.append(task_hint)
        return {
            "findings": ["OK"],
            "bounce_to_drafter": False,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(fake_llm, role_config, registry)

    await node({
        "proposal": {},
        "extraction_mode": "config_only",
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert captured_task_hints == [None]


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_governance_review_prompt_includes_enum_gap_proposals() -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})
    captured_messages: list[list[dict[str, str]]] = []

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        captured_messages.append(messages)
        return {
            "findings": ["warning: weak enum gap"],
            "bounce_to_drafter": False,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(fake_llm, role_config, registry)

    result = await node({
        "proposal": None,
        "enum_gap_proposals": [
            {
                "enum_path": "macro_foundry.enums.series.SeasonalAdjustment",
                "proposed_value": "TCA",
                "rationale": "Provider publishes trend-cycle adjusted data.",
            }
        ],
        "extraction_mode": "config_only",
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert "enum_gap_proposals" in captured_messages[0][0]["content"]
    assert "TCA" in captured_messages[0][0]["content"]
    assert result["governance_review"]["findings"][0] == "warning: weak enum gap"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_governance_review_llm_call_records_task_hint_when_custom_python() -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        return {
            "findings": ["OK"],
            "bounce_to_drafter": False,
            "prompt_tokens": 200,
            "completion_tokens": 100,
            "total_tokens": 300,
            "cost_estimate_usd": 0.003,
            "latency_ms": 350,
        }

    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(fake_llm, role_config, registry)

    result = await node({
        "proposal": {},
        "extraction_mode": "custom_python",
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    call = result["llm_calls"][0]
    assert call["task_hint"] == "selector_code_review"


# ---------------------------------------------------------------------------
# Slice 5 — Read-only enforcement: bound_tools excludes write tools
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_governance_reviewer_bound_tools_excludes_write_tools() -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:  # pragma: no cover
        return {}

    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(fake_llm, role_config, registry)

    bound: frozenset[str] = node.bound_tools  # type: ignore[attr-defined]
    write_tools = {"macrodb_write", "macrodb_write_proposals", "selector_sandbox"}
    assert bound.isdisjoint(write_tools), f"write tools found in bound_tools: {bound & write_tools}"


@pytest.mark.no_db
def test_data_correctness_reviewer_bound_tools_excludes_write_tools() -> None:
    from macro_foundry.agent.graph import make_data_correctness_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:  # pragma: no cover
        return {}

    role_config = default_role_configs()[AgentRole.DATA_CORRECTNESS_REVIEWER]
    node = make_data_correctness_review_node(fake_llm, role_config, registry)

    bound: frozenset[str] = node.bound_tools  # type: ignore[attr-defined]
    write_tools = {"macrodb_write", "macrodb_write_proposals", "selector_sandbox"}
    assert bound.isdisjoint(write_tools), f"write tools found in bound_tools: {bound & write_tools}"


# ---------------------------------------------------------------------------
# Slice 6 — data_correctness_review node
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_data_correctness_review_node_writes_review_bundle() -> None:
    from macro_foundry.agent.graph import make_data_correctness_review_node
    from macro_foundry.agent.review import ReviewBundle
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        return {
            "findings": ["Magnitude band matches Q3 2025 published value."],
            "bounce_to_drafter": False,
            "prompt_tokens": 120,
            "completion_tokens": 60,
            "total_tokens": 180,
            "cost_estimate_usd": 0.0015,
            "latency_ms": 250,
        }

    role_config = default_role_configs()[AgentRole.DATA_CORRECTNESS_REVIEWER]
    node = make_data_correctness_review_node(fake_llm, role_config, registry)

    result = await node({
        "proposal": {"series": {"code": "US_CPI_SA_M"}},
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert result["data_correctness_review"] is not None
    bundle = ReviewBundle.model_validate(result["data_correctness_review"])
    assert bundle.specialty == "data_correctness"
    assert bundle.bounce_to_drafter is False
    assert bundle.review_cycle == 1


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_data_correctness_review_node_records_llm_call() -> None:
    from macro_foundry.agent.graph import make_data_correctness_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        return {
            "findings": ["OK"],
            "bounce_to_drafter": False,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    role_config = default_role_configs()[AgentRole.DATA_CORRECTNESS_REVIEWER]
    node = make_data_correctness_review_node(fake_llm, role_config, registry)

    result = await node({
        "proposal": {},
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert len(result["llm_calls"]) == 1
    call = result["llm_calls"][0]
    assert call["role"] == "data_correctness_reviewer"


# ---------------------------------------------------------------------------
# Slice 7 — review_cycle increments; soft cap of 3 visible in bundle
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_review_cycle_increments_from_state() -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.review import ReviewBundle
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        return {
            "findings": ["Still some issues."],
            "bounce_to_drafter": True,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(fake_llm, role_config, registry)

    # Simulate second cycle (review_cycle already at 1 from previous cycle)
    result = await node({
        "proposal": {},
        "extraction_mode": "config_only",
        "review_cycle": 1,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    bundle = ReviewBundle.model_validate(result["governance_review"])
    assert bundle.review_cycle == 2
    assert result["review_cycle"] == 2
    assert bundle.bounce_to_drafter is True


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_review_cycle_reaches_soft_cap_3() -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.review import ReviewBundle
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        return {
            "findings": ["Cycle 3 bounce."],
            "bounce_to_drafter": True,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(fake_llm, role_config, registry)

    result = await node({
        "proposal": {},
        "extraction_mode": "config_only",
        "review_cycle": 2,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    bundle = ReviewBundle.model_validate(result["governance_review"])
    assert bundle.review_cycle == 3


# ---------------------------------------------------------------------------
# Slice 8 — Fan-out integration: config_only and custom_python sessions
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_config_only_session_exercises_2_reviewer_calls() -> None:
    """config_only: governance + data_correctness each called once; no selector skill."""
    from macro_foundry.agent.graph import make_data_correctness_review_node, make_governance_review_node
    from macro_foundry.agent.review import ReviewBundle
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})
    role_configs = default_role_configs()

    gov_calls: list[str | None] = []
    dc_calls: list[str | None] = []

    async def fake_gov_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        gov_calls.append(task_hint)
        return {
            "findings": ["Governance OK"],
            "bounce_to_drafter": False,
            "prompt_tokens": 150,
            "completion_tokens": 80,
            "total_tokens": 230,
            "cost_estimate_usd": 0.002,
            "latency_ms": 300,
        }

    async def fake_dc_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        dc_calls.append(task_hint)
        return {
            "findings": ["Data correctness OK"],
            "bounce_to_drafter": False,
            "prompt_tokens": 120,
            "completion_tokens": 60,
            "total_tokens": 180,
            "cost_estimate_usd": 0.0015,
            "latency_ms": 250,
        }

    gov_node = make_governance_review_node(
        fake_gov_llm, role_configs[AgentRole.GOVERNANCE_REVIEWER], registry
    )
    dc_node = make_data_correctness_review_node(
        fake_dc_llm, role_configs[AgentRole.DATA_CORRECTNESS_REVIEWER], registry
    )

    state = {
        "proposal": {"concept": {"code": "CPI"}},
        "extraction_mode": "config_only",
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    }
    gov_update = await gov_node(state)
    final = {
        **state,
        **gov_update,
        "llm_calls": state["llm_calls"] + gov_update["llm_calls"],
    }
    dc_update = await dc_node(final)
    final = {
        **final,
        **dc_update,
        "llm_calls": final["llm_calls"] + dc_update["llm_calls"],
    }

    # Exactly 2 reviewer LLM calls
    assert len(gov_calls) == 1
    assert len(dc_calls) == 1
    # config_only: no task_hint on governance
    assert gov_calls[0] is None

    # Both bundles present
    gov_bundle = ReviewBundle.model_validate(final["governance_review"])
    dc_bundle = ReviewBundle.model_validate(final["data_correctness_review"])
    assert gov_bundle.specialty == "governance"
    assert dc_bundle.specialty == "data_correctness"

    # Total 2 LLM call records in state
    assert len(final["llm_calls"]) == 2
    roles = {c["role"] for c in final["llm_calls"]}
    assert roles == {"governance_reviewer", "data_correctness_reviewer"}


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_custom_python_session_exercises_2_reviewer_calls_with_selector_skill() -> None:
    """custom_python: governance fires with task_hint=selector_code_review; still 2 total calls."""
    from macro_foundry.agent.graph import make_data_correctness_review_node, make_governance_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})
    role_configs = default_role_configs()

    gov_calls: list[str | None] = []
    dc_calls: list[str | None] = []

    async def fake_gov_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        gov_calls.append(task_hint)
        return {
            "findings": ["Selector code OK"],
            "bounce_to_drafter": False,
            "prompt_tokens": 200,
            "completion_tokens": 120,
            "total_tokens": 320,
            "cost_estimate_usd": 0.003,
            "latency_ms": 400,
        }

    async def fake_dc_llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        dc_calls.append(task_hint)
        return {
            "findings": ["Data OK"],
            "bounce_to_drafter": False,
            "prompt_tokens": 120,
            "completion_tokens": 60,
            "total_tokens": 180,
            "cost_estimate_usd": 0.0015,
            "latency_ms": 250,
        }

    gov_node = make_governance_review_node(
        fake_gov_llm, role_configs[AgentRole.GOVERNANCE_REVIEWER], registry
    )
    dc_node = make_data_correctness_review_node(
        fake_dc_llm, role_configs[AgentRole.DATA_CORRECTNESS_REVIEWER], registry
    )

    state = {
        "proposal": {"proposed_scripts": ["import requests"]},
        "extraction_mode": "custom_python",
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    }
    gov_update = await gov_node(state)
    final = {
        **state,
        **gov_update,
        "llm_calls": state["llm_calls"] + gov_update["llm_calls"],
    }
    dc_update = await dc_node(final)
    final = {
        **final,
        **dc_update,
        "llm_calls": final["llm_calls"] + dc_update["llm_calls"],
    }

    # Still exactly 2 LLM calls — not 3
    assert len(gov_calls) == 1
    assert len(dc_calls) == 1
    # Governance gets task_hint for selector code review
    assert gov_calls[0] == "selector_code_review"

    assert len(final["llm_calls"]) == 2
