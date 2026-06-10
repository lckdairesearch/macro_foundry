"""Tests for apply_catalog selector promotion step (issue 46)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeProposalResult:
    proposal_id: str = "prop-1"
    item_id: str = "item-1"
    series_id: str = "series-1"
    family_id: str = "family-1"
    concept_id: str = "concept-1"
    feed_id: str = "feed-1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "item_id": self.item_id,
            "series_id": self.series_id,
            "family_id": self.family_id,
            "concept_id": self.concept_id,
            "feed_id": self.feed_id,
        }


class FakeWriteTools:
    def __init__(self, result: FakeProposalResult | None = None) -> None:
        self._result = result or FakeProposalResult()
        self.propose_calls: list[Any] = []
        self.sha_calls: list[Any] = []
        self.cred_calls: list[Any] = []

    async def propose_create_series(self, args: Any) -> dict[str, Any]:
        self.propose_calls.append(args)
        return self._result.as_dict()

    async def record_suggest_human_apply(self, args: Any) -> dict[str, Any]:
        self.sha_calls.append(args)
        return {}

    async def apply_credential_gap_resolutions(self, args: Any) -> dict[str, Any]:
        self.cred_calls.append(args)
        return {}


def _approved_state(
    *,
    session_id: str = "sess-1",
    proposed_selector_path: str | None = None,
    proposed_selector_name: str | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "gate_1_approved": True,
        "session_metadata": {"session_id": session_id},
        "proposal": {
            "concept": {"action": "new", "code": "CPI", "name": "CPI"},
            "feed": {"selector_type": "custom_cpi", "cron_schedule": "0 14 * * 5", "feed_method": "api"},
        },
        "suggest_human_apply": [],
        "credential_gap_resolutions": [],
        "harmonisation_items": [],
        "llm_calls": [],
        "node_transitions": [],
    }
    if proposed_selector_path is not None:
        state["proposed_selector_path"] = proposed_selector_path
    if proposed_selector_name is not None:
        state["proposed_selector_name"] = proposed_selector_name
    return state


# ---------------------------------------------------------------------------
# Cycle 8: apply_catalog copies sandbox selector and patches __init__.py
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_apply_catalog_copies_sandbox_selector_to_runtime(tmp_path: Path) -> None:
    from macro_foundry.agent.catalog import make_apply_catalog_node

    selectors_dir = tmp_path / "selectors"
    selectors_dir.mkdir(parents=True)
    init_file = selectors_dir / "__init__.py"
    init_file.write_text("# existing registry\n_SELECTORS: dict = {}\n")

    sandbox_dir = tmp_path / "sandbox" / "sess-1"
    sandbox_dir.mkdir(parents=True)
    selector_file = sandbox_dir / "custom_cpi.py"
    selector_code = "class CustomCpiSelector:\n    name = 'custom_cpi'\n"
    selector_file.write_text(selector_code)

    fake_tests_passed: list[str] = []

    async def fake_run_tests(selector_name: str) -> dict[str, Any]:
        fake_tests_passed.append(selector_name)
        return {"ok": True, "output": "1 passed"}

    write_tools = FakeWriteTools()
    node = make_apply_catalog_node(
        write_tools=write_tools,
        selectors_runtime_dir=selectors_dir,
        run_selector_tests=fake_run_tests,
    )

    state = _approved_state(
        proposed_selector_path=str(selector_file),
        proposed_selector_name="custom_cpi",
    )
    result = await node(state)

    promoted = selectors_dir / "custom_cpi.py"
    assert promoted.exists(), "selector file must be copied to runtime dir"
    assert promoted.read_text() == selector_code

    assert fake_tests_passed == ["custom_cpi"]
    assert result["gate_1_applied"] is True


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_apply_catalog_skips_promotion_when_no_sandbox_path(tmp_path: Path) -> None:
    from macro_foundry.agent.catalog import make_apply_catalog_node

    selectors_dir = tmp_path / "selectors"
    selectors_dir.mkdir()

    run_called: list[str] = []

    async def fake_run_tests(name: str) -> dict[str, Any]:
        run_called.append(name)
        return {"ok": True, "output": "1 passed"}

    write_tools = FakeWriteTools()
    node = make_apply_catalog_node(
        write_tools=write_tools,
        selectors_runtime_dir=selectors_dir,
        run_selector_tests=fake_run_tests,
    )

    state = _approved_state()  # no proposed_selector_path
    result = await node(state)

    assert run_called == [], "run_selector_tests must not be called for config_only proposals"
    assert result["gate_1_applied"] is True


# ---------------------------------------------------------------------------
# Cycle 9: apply_catalog aborts when selector tests fail
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_apply_catalog_aborts_when_selector_tests_fail(tmp_path: Path) -> None:
    from macro_foundry.agent.catalog import make_apply_catalog_node

    selectors_dir = tmp_path / "selectors"
    selectors_dir.mkdir()

    sandbox_dir = tmp_path / "sandbox" / "sess-1"
    sandbox_dir.mkdir(parents=True)
    selector_file = sandbox_dir / "bad_selector.py"
    selector_file.write_text("class Bad:\n    name = 'bad_selector'\n")

    async def fake_run_tests(name: str) -> dict[str, Any]:
        return {"ok": False, "output": "FAILED test_bad_selector.py::test_extract"}

    write_tools = FakeWriteTools()
    node = make_apply_catalog_node(
        write_tools=write_tools,
        selectors_runtime_dir=selectors_dir,
        run_selector_tests=fake_run_tests,
    )

    state = _approved_state(
        proposed_selector_path=str(selector_file),
        proposed_selector_name="bad_selector",
    )

    with pytest.raises(RuntimeError, match="selector tests failed"):
        await node(state)

    # propose_create_series must NOT have been called — abort is before catalog write
    assert write_tools.propose_calls == [], "catalog write must not happen when tests fail"


# ---------------------------------------------------------------------------
# Cycle 10: no git calls ever invoked by the node
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_apply_catalog_does_not_call_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from macro_foundry.agent.catalog import make_apply_catalog_node

    selectors_dir = tmp_path / "selectors"
    selectors_dir.mkdir()
    sandbox_dir = tmp_path / "sandbox" / "sess-1"
    sandbox_dir.mkdir(parents=True)
    selector_file = sandbox_dir / "custom_cpi.py"
    selector_file.write_text("class CustomCpiSelector:\n    name = 'custom_cpi'\n")

    git_called: list[str] = []

    import subprocess

    original_run = subprocess.run

    def spy_run(args: Any, *a: Any, **kw: Any) -> Any:
        cmd = args[0] if isinstance(args, (list, tuple)) else args
        if "git" in str(cmd):
            git_called.append(str(args))
        return original_run(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", spy_run)

    async def fake_run_tests(name: str) -> dict[str, Any]:
        return {"ok": True, "output": "1 passed"}

    write_tools = FakeWriteTools()
    node = make_apply_catalog_node(
        write_tools=write_tools,
        selectors_runtime_dir=selectors_dir,
        run_selector_tests=fake_run_tests,
    )

    await node(_approved_state(
        proposed_selector_path=str(selector_file),
        proposed_selector_name="custom_cpi",
    ))

    assert git_called == [], f"git must never be called by apply_catalog; got: {git_called}"
