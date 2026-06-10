"""Integration test: full custom_python onboarding from drafter through promotion (issue 46)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class _NoopChannel:
    async def emit(self, event: Any) -> None:
        pass

    async def prompt(self, prompt: Any) -> Any:
        class _R:
            text = "/save"
        return _R()


class _NoopWriteTools:
    async def propose_create_series(self, args: Any) -> dict[str, Any]:
        return {
            "proposal_id": "00000000-0000-0000-0000-000000000001",
            "item_id": "00000000-0000-0000-0000-000000000002",
            "series_id": "00000000-0000-0000-0000-000000000003",
            "family_id": "00000000-0000-0000-0000-000000000004",
            "concept_id": "00000000-0000-0000-0000-000000000005",
            "feed_id": "00000000-0000-0000-0000-000000000006",
        }

    async def record_suggest_human_apply(self, args: Any) -> dict[str, Any]:
        return {}

    async def apply_credential_gap_resolutions(self, args: Any) -> dict[str, Any]:
        return {}

    async def trigger_feed_execution(self, args: Any) -> dict[str, Any]:
        return {"run_log_id": "run-1"}


class _NoopRunLogs:
    async def get_ingestion_run_log(self, run_log_id: str) -> dict[str, Any]:
        return {
            "run_log_id": run_log_id,
            "status": "completed",
            "rows_written": 10,
            "error_message": None,
        }


class _NoopPackageStore:
    async def save_onboarding_package(self, package: dict[str, Any]) -> dict[str, Any]:
        return {"package_id": "pkg-1", **package}


async def _reviewer_llm(messages: list[dict[str, str]], **_: Any) -> dict[str, Any]:
    return {
        "findings": [],
        "bounce_to_drafter": False,
        "prompt_tokens": 5,
        "completion_tokens": 3,
        "total_tokens": 8,
        "cost_estimate_usd": 0.0,
        "latency_ms": 5,
    }


async def _approval_llm(state: dict[str, Any], **_: Any) -> dict[str, Any]:
    return {"outcome": "approve", "rationale": "LGTM"}


async def _approve_picker(*_: Any, **__: Any) -> str:
    return "approve"


async def _test_reviewer(messages: list[dict[str, str]], **_: Any) -> dict[str, Any]:
    return {
        "outcome": "pass",
        "summary": "Tests passed.",
        "prompt_tokens": 5,
        "completion_tokens": 3,
        "total_tokens": 8,
        "cost_estimate_usd": 0.0,
        "latency_ms": 5,
    }


# ---------------------------------------------------------------------------
# Integration: full custom_python path
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_custom_python_full_path_draft_validate_review_gate_apply(tmp_path: Path) -> None:
    """Full custom_python onboarding: draft_script → validate_script → governance_review
    → data_correctness_review → gate_1_wait (approve) → apply_catalog with promotion."""
    from macro_foundry.agent.graph import build_onboarding_graph
    from macro_foundry.agent.roles import default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    sandbox_base = tmp_path / "sandbox"
    selectors_dir = tmp_path / "selectors"
    selectors_dir.mkdir()

    selector_code = "class CustomCpiSelector:\n    name = 'custom_cpi'\n"

    async def fake_research_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "source_summary": "Provider returns bespoke nested JSON.",
            "existing_catalog_hits": [],
            "ambiguity_flags": [],
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cost_estimate_usd": 0.0,
            "latency_ms": 10,
        }

    async def fake_cohort_lookup(catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        return {"cohort_a": [], "cohort_b": [], "cohort_c": []}

    async def fake_classify(source_summary: str) -> str:
        return "custom_python"

    async def fake_draft_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "proposal": {
                "concept": {"action": "new", "code": "CPI", "name": "CPI"},
                "family": {"action": "new", "code": "HK_CPI", "name": "HK CPI", "concept_code": "CPI", "geography_code": "HKG"},
                "series": {
                    "action": "new",
                    "code": "HK_CPI_SA_M",
                    "name": "HK CPI SA Monthly",
                    "frequency": "monthly",
                    "measure": "index_level",
                    "unit_kind": "pure",
                    "temporal_stock_flow": "index",
                    "unit_scale": "one",
                    "seasonal_adjustment": "NSA",
                },
                "source": {"provider_name": "CensusD", "external_code": "HK_CPI"},
                "feed": {"selector_type": "custom_cpi", "cron_schedule": "0 14 * * 5", "feed_method": "api"},
                "family_member": {"variant": "SA"},
                "hierarchy_edges": [],
            },
            "enum_gap_proposals": [],
            "harmonisation_items": [],
            "suggest_human_apply": [],
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cost_estimate_usd": 0.0,
            "latency_ms": 10,
        }

    async def fake_script_drafter_llm(messages: list[dict[str, str]], **_: Any) -> dict[str, Any]:
        return {
            "selector_name": "custom_cpi",
            "selector_code": selector_code,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cost_estimate_usd": 0.0,
            "latency_ms": 10,
        }

    async def fake_probe(selector_path: str, probe_payload: Any) -> dict[str, Any]:
        return {"ok": True}

    tests_run: list[str] = []

    async def fake_run_selector_tests(selector_name: str) -> dict[str, Any]:
        tests_run.append(selector_name)
        return {"ok": True, "output": "1 passed"}

    registry = SkillRegistry({})
    role_configs = default_role_configs()
    checkpointer = MemorySaver()

    graph = build_onboarding_graph(
        checkpointer=checkpointer,
        research_llm=fake_research_llm,
        cohort_lookup=fake_cohort_lookup,
        extraction_mode_classifier=fake_classify,
        draft_llm=fake_draft_llm,
        script_drafter_llm=fake_script_drafter_llm,
        script_sandbox_base=sandbox_base,
        script_probe=fake_probe,
        selectors_runtime_dir=selectors_dir,
        run_selector_tests=fake_run_selector_tests,
        governance_llm=_reviewer_llm,
        data_correctness_llm=_reviewer_llm,
        approval_llm=_approval_llm,
        gate_1_picker=_approve_picker,
        channel=_NoopChannel(),
        write_tools=_NoopWriteTools(),
        run_logs=_NoopRunLogs(),
        test_reviewer=_test_reviewer,
        package_store=_NoopPackageStore(),
        role_configs=role_configs,
        registry=registry,
    )

    config = {"configurable": {"thread_id": "integ-custom-python-1"}}
    final_state = await graph.ainvoke(
        {"pending_input": "Onboard HK CPI via CensusD bespoke JSON"},
        config,
    )

    # Extraction mode was correctly classified
    assert final_state["extraction_mode"] == "custom_python"

    # Sandbox file was written
    assert final_state.get("proposed_selector_name") == "custom_cpi"
    proposed_path = Path(final_state["proposed_selector_path"])
    assert proposed_path.exists()
    assert proposed_path.read_text() == selector_code

    # Validation succeeded
    assert final_state.get("validation_result") == "ok"

    # Governance reviewer received the sandbox content (task_hint set)
    gov_calls = [c for c in final_state.get("llm_calls", []) if c.get("role") == "governance_reviewer"]
    assert gov_calls, "governance_reviewer LLM must be called"
    assert gov_calls[0].get("task_hint") == "selector_code_review"

    # Gate 1 was approved and catalog written
    assert final_state.get("gate_1_approved") is True
    assert final_state.get("gate_1_applied") is True

    # Promotion: selector copied to runtime dir
    promoted = selectors_dir / "custom_cpi.py"
    assert promoted.exists(), "promoted selector must exist in runtime dir"
    assert promoted.read_text() == selector_code

    # Selector tests were run as part of promotion
    assert tests_run == ["custom_cpi"]

    # Hard invariant: no git calls (validated separately in test_selector_promotion.py)
    # Package emitted
    assert final_state.get("onboarding_package"), "onboarding_package must be emitted"
