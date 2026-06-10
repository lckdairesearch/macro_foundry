"""apply_catalog node — writes approved proposals to the catalog (issue 47)."""

from __future__ import annotations

import shutil
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

# Callable injected into make_apply_catalog_node for selector test execution.
# Receives the selector_name (not path); returns {"ok": bool, "output": str}.
RunSelectorTestsCallable = Callable[[str], Awaitable[dict[str, Any]]]


class WriteToolsProtocol(Protocol):
    """Minimal write-tools interface the apply_catalog node depends on."""

    async def propose_create_series(self, args: Any) -> dict[str, Any]: ...

    async def record_suggest_human_apply(self, args: Any) -> dict[str, Any]: ...

    async def apply_credential_gap_resolutions(self, args: Any) -> dict[str, Any]: ...


def make_apply_catalog_node(
    *,
    write_tools: WriteToolsProtocol,
    selectors_runtime_dir: Path | None = None,
    run_selector_tests: RunSelectorTestsCallable | None = None,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return the apply_catalog node.

    Reads gate-1-approved proposal state, writes catalog rows transactionally,
    and records suggest_human_apply items as pending_human_apply in change_proposals.

    When proposed_selector_path and proposed_selector_name are set in state and
    selectors_runtime_dir is provided, the promotion step runs before the catalog
    write: the sandbox file is copied to selectors_runtime_dir/<name>.py and
    run_selector_tests is called. If tests fail the node raises RuntimeError and
    the catalog write is aborted. No git calls are made at any point.

    Refuses to run when gate_1_approved is not True.
    """

    async def _apply_catalog_node(state: dict[str, Any]) -> dict[str, Any]:
        from macro_foundry.agent.onboarding_state import NodeTransition
        from macro_foundry.mcp.write_tools import (
            ApplyCredentialGapResolutionsArgs,
            ProposeCreateSeriesArgs,
            RecordSuggestHumanApplyArgs,
        )

        if not state.get("gate_1_approved"):
            raise RuntimeError(
                "apply_catalog requires gate_1_approved=True; "
                "the executor cannot run before an approval flag is set in state"
            )

        sandbox_path: str | None = state.get("proposed_selector_path")
        selector_name: str | None = state.get("proposed_selector_name")

        if sandbox_path and selector_name and selectors_runtime_dir is not None:
            await _promote_selector(
                sandbox_path=Path(sandbox_path),
                selector_name=selector_name,
                runtime_dir=selectors_runtime_dir,
                run_tests=run_selector_tests,
            )

        session_id: str = (state.get("session_metadata") or {}).get("session_id", "")
        proposal_dict: dict[str, Any] = state.get("proposal") or {}
        sha_items: list[dict[str, Any]] = list(state.get("suggest_human_apply") or [])
        credential_resolutions: list[dict[str, Any]] = list(
            state.get("credential_gap_resolutions") or []
        )

        proposal_result = await write_tools.propose_create_series(
            ProposeCreateSeriesArgs(
                session_id=session_id,
                payload=proposal_dict,
                rationale="Gate 1 approved",
                harmonisation_items=list(state.get("harmonisation_items") or []),
            )
        )
        proposal_id = proposal_result.get("proposal_id")

        if sha_items:
            await write_tools.record_suggest_human_apply(
                RecordSuggestHumanApplyArgs(
                    items=sha_items,
                    session_id=session_id,
                    proposal_id=proposal_id,
                )
            )

        if credential_resolutions:
            await write_tools.apply_credential_gap_resolutions(
                ApplyCredentialGapResolutionsArgs(resolutions=credential_resolutions)
            )

        now = datetime.now(timezone.utc)
        return {
            "gate_1_applied": True,
            "applied_catalog": {
                key: proposal_result[key]
                for key in ("proposal_id", "item_id", "series_id", "family_id", "concept_id", "feed_id")
                if key in proposal_result
            },
            "node_transitions": [
                NodeTransition(
                    node="apply_catalog",
                    event="completed",
                    created_at=now,
                ).model_dump(mode="json"),
            ],
        }

    return _apply_catalog_node


async def _promote_selector(
    *,
    sandbox_path: Path,
    selector_name: str,
    runtime_dir: Path,
    run_tests: RunSelectorTestsCallable | None,
) -> None:
    """Copy sandbox selector to the runtime registry and run its tests.

    Raises RuntimeError if tests fail. Never calls git.
    The only write outside the sandbox is the single copy into runtime_dir.
    """
    dest = runtime_dir / f"{selector_name}.py"
    shutil.copy2(sandbox_path, dest)

    if run_tests is not None:
        result = await run_tests(selector_name)
        if not result.get("ok"):
            dest.unlink(missing_ok=True)
            raise RuntimeError(
                f"selector tests failed for {selector_name!r}: {result.get('output', '')}"
            )


__all__ = ["RunSelectorTestsCallable", "WriteToolsProtocol", "make_apply_catalog_node"]
