"""Tests for draft_script and validate_script nodes (issue 46)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_llm_response(
    *,
    selector_name: str = "custom_cpi",
    selector_code: str = "class CustomCpiSelector:\n    name = 'custom_cpi'\n",
) -> dict[str, Any]:
    return {
        "selector_name": selector_name,
        "selector_code": selector_code,
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
        "cost_estimate_usd": 0.002,
        "latency_ms": 300,
    }


def _base_state(
    *,
    session_id: str = "test-session-abc",
    extraction_mode: str = "custom_python",
    source_summary: str = "Provider returns custom nested JSON.",
    proposed_selector_path: str | None = None,
    review_cycle: int = 0,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "session_metadata": {"session_id": session_id},
        "extraction_mode": extraction_mode,
        "source_summary": source_summary,
        "proposal": {
            "feed": {"selector_type": "custom_cpi", "cron_schedule": "0 14 * * 5", "feed_method": "api"}
        },
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
        "review_cycle": review_cycle,
    }
    if proposed_selector_path is not None:
        state["proposed_selector_path"] = proposed_selector_path
    return state


# ---------------------------------------------------------------------------
# Cycle 1: draft_script writes only to sandbox path
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_script_writes_file_under_sandbox_path(tmp_path: Path) -> None:
    from macro_foundry.agent.script_drafter import make_draft_script_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    async def fake_llm(messages: list[dict[str, str]], **_: Any) -> dict[str, Any]:
        return _fake_llm_response()

    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_script_node(fake_llm, role_config, sandbox_base=tmp_path)
    state = _base_state(session_id="test-session-abc")

    result = await node(state)

    expected_path = tmp_path / "test-session-abc" / "custom_cpi.py"
    assert expected_path.exists(), "sandbox file must be written"
    assert result["proposed_selector_path"] == str(expected_path)
    assert result["proposed_selector_name"] == "custom_cpi"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_script_never_writes_under_src(tmp_path: Path) -> None:
    from macro_foundry.agent.script_drafter import make_draft_script_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    src_root = tmp_path / "src"
    src_root.mkdir()
    sandbox = tmp_path / "agent_workspace" / "proposed_selectors"

    async def fake_llm(messages: list[dict[str, str]], **_: Any) -> dict[str, Any]:
        return _fake_llm_response(selector_name="evil_selector")

    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_script_node(fake_llm, role_config, sandbox_base=sandbox)
    state = _base_state(session_id="s1")

    await node(state)

    # Nothing should appear under src/
    written = list(src_root.rglob("*.py"))
    assert written == [], f"draft_script wrote into src/: {written}"


# ---------------------------------------------------------------------------
# Cycle 2: draft_script skips when extraction_mode != "custom_python"
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_script_skips_for_config_only_mode(tmp_path: Path) -> None:
    from macro_foundry.agent.script_drafter import make_draft_script_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    called: list[bool] = []

    async def fake_llm(messages: list[dict[str, str]], **_: Any) -> dict[str, Any]:
        called.append(True)
        return _fake_llm_response()

    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_script_node(fake_llm, role_config, sandbox_base=tmp_path)
    state = _base_state(extraction_mode="config_only")

    result = await node(state)

    assert not called, "LLM must not be called for config_only mode"
    assert result.get("proposed_selector_path") is None
    assert result.get("proposed_selector_name") is None
    transitions = result.get("node_transitions", [])
    assert any("skipped" in t.get("event", "") for t in transitions)


# ---------------------------------------------------------------------------
# Cycle 3: draft_script records LLM call
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_script_records_llm_call(tmp_path: Path) -> None:
    from macro_foundry.agent.script_drafter import make_draft_script_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    async def fake_llm(messages: list[dict[str, str]], **_: Any) -> dict[str, Any]:
        return _fake_llm_response(selector_name="custom_cpi", selector_code="class X:\n    name='x'\n")

    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_script_node(fake_llm, role_config, sandbox_base=tmp_path)

    result = await node(_base_state())

    assert len(result["llm_calls"]) == 1
    call = result["llm_calls"][0]
    assert call["prompt_tokens"] == 120
    assert call["total_tokens"] == 200


# ---------------------------------------------------------------------------
# Cycle 4: validate_script returns "ok" when probe succeeds
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_validate_script_ok_when_probe_succeeds(tmp_path: Path) -> None:
    from macro_foundry.agent.script_drafter import make_validate_script_node

    selector_code = textwrap.dedent("""\
        from macro_foundry.ingestion.runtime.types import ExtractionResult, ValidationResult

        class CustomCpiSelector:
            name = "custom_cpi"
            config_schema: dict = {}

            def validate(self, config):
                return ValidationResult(is_valid=True)

            def extract(self, payload, config):
                return ExtractionResult(outcome="empty", observations=[])
    """)

    sandbox_dir = tmp_path / "s1"
    sandbox_dir.mkdir()
    selector_file = sandbox_dir / "custom_cpi.py"
    selector_file.write_text(selector_code)

    async def fake_probe(selector_path: str, probe_payload: Any) -> dict[str, Any]:
        return {"ok": True}

    node = make_validate_script_node(probe_callable=fake_probe)
    state = _base_state(proposed_selector_path=str(selector_file))

    result = await node(state)

    assert result["validation_result"] == "ok"
    assert result.get("validation_error") is None
    transitions = result.get("node_transitions", [])
    assert any(t.get("event") == "ok" for t in transitions)


# ---------------------------------------------------------------------------
# Cycle 5: validate_script returns "failed" and records error
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_validate_script_failed_when_probe_raises(tmp_path: Path) -> None:
    from macro_foundry.agent.script_drafter import make_validate_script_node

    sandbox_dir = tmp_path / "s1"
    sandbox_dir.mkdir()
    selector_file = sandbox_dir / "bad_selector.py"
    selector_file.write_text("this is not valid python syntax ><")

    async def fake_probe(selector_path: str, probe_payload: Any) -> dict[str, Any]:
        raise SyntaxError("invalid syntax")

    node = make_validate_script_node(probe_callable=fake_probe)
    state = _base_state(proposed_selector_path=str(selector_file))

    result = await node(state)

    assert result["validation_result"] == "failed"
    assert result["validation_error"] is not None
    assert "syntax" in result["validation_error"].lower()
    transitions = result.get("node_transitions", [])
    assert any(t.get("event") == "failed" for t in transitions)


# ---------------------------------------------------------------------------
# Cycle 6: edge from validate_script — ok goes to governance, failed loops back
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_edge_validate_script_ok_goes_to_governance_review() -> None:
    from langgraph.graph import END
    from macro_foundry.agent.graph import EDGE_NEXT_FROM_VALIDATE_SCRIPT

    state = _base_state(review_cycle=1)
    state["validation_result"] = "ok"

    assert EDGE_NEXT_FROM_VALIDATE_SCRIPT(state) == "governance_review"


@pytest.mark.no_db
def test_edge_validate_script_failed_loops_to_draft_script_within_cap() -> None:
    from macro_foundry.agent.graph import EDGE_NEXT_FROM_VALIDATE_SCRIPT

    state = _base_state(review_cycle=2)
    state["validation_result"] = "failed"

    assert EDGE_NEXT_FROM_VALIDATE_SCRIPT(state) == "draft_script"


@pytest.mark.no_db
def test_edge_validate_script_failed_at_cap_goes_to_end() -> None:
    from langgraph.graph import END
    from macro_foundry.agent.graph import EDGE_NEXT_FROM_VALIDATE_SCRIPT

    state = _base_state(review_cycle=3)
    state["validation_result"] = "failed"

    assert EDGE_NEXT_FROM_VALIDATE_SCRIPT(state) == END


# ---------------------------------------------------------------------------
# Cycle 7: governance_review injects sandbox file content when custom_python
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_governance_review_injects_sandbox_content_for_custom_python(tmp_path: Path) -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    selector_code = "class CustomCpiSelector:\n    name = 'custom_cpi'\n"
    selector_file = tmp_path / "custom_cpi.py"
    selector_file.write_text(selector_code)

    captured_messages: list[list[dict[str, str]]] = []

    async def fake_llm(messages: list[dict[str, str]], **_: Any) -> dict[str, Any]:
        captured_messages.append(messages)
        return {
            "findings": [],
            "bounce_to_drafter": False,
            "prompt_tokens": 50,
            "completion_tokens": 30,
            "total_tokens": 80,
            "cost_estimate_usd": 0.0008,
            "latency_ms": 150,
        }

    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(fake_llm, role_config, SkillRegistry({}))

    state = {
        "proposal": {"feed": {"selector_type": "custom_cpi"}},
        "enum_gap_proposals": [],
        "extraction_mode": "custom_python",
        "proposed_selector_path": str(selector_file),
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    }

    await node(state)

    assert len(captured_messages) == 1
    content = captured_messages[0][0]["content"]
    assert selector_code in content, "sandbox file content must appear in governance LLM message"
