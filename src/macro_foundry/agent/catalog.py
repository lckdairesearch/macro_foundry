"""apply_catalog node — writes approved proposals to the catalog (issue 47)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Protocol

from macro_foundry.agent.proposal import DraftProposal


class WriteToolsProtocol(Protocol):
    """Minimal write-tools interface the apply_catalog node depends on."""

    async def propose_create_series(self, args: Any) -> dict[str, Any]: ...

    async def record_suggest_human_apply(self, args: Any) -> dict[str, Any]: ...


def make_apply_catalog_node(
    *,
    write_tools: WriteToolsProtocol,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return the apply_catalog node.

    Reads gate-1-approved proposal state, writes catalog rows transactionally,
    and records suggest_human_apply items as pending_human_apply in change_proposals.

    Refuses to run when gate_1_approved is not True.
    """

    async def _apply_catalog_node(state: dict[str, Any]) -> dict[str, Any]:
        from macro_foundry.agent.onboarding_state import NodeTransition
        from macro_foundry.mcp.write_tools import (
            ProposeCreateSeriesArgs,
            RecordSuggestHumanApplyArgs,
        )

        if not state.get("gate_1_approved"):
            raise RuntimeError(
                "apply_catalog requires gate_1_approved=True; "
                "the executor cannot run before an approval flag is set in state"
            )

        session_id: str = (state.get("session_metadata") or {}).get("session_id", "")
        proposal_dict: dict[str, Any] = state.get("proposal") or {}
        sha_items: list[dict[str, Any]] = list(state.get("suggest_human_apply_items") or [])

        proposal_result = await write_tools.propose_create_series(
            ProposeCreateSeriesArgs(
                session_id=session_id,
                payload=proposal_dict,
                rationale="Gate 1 approved",
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

        now = datetime.now(timezone.utc)
        return {
            "gate_1_applied": True,
            "node_transitions": [
                NodeTransition(
                    node="apply_catalog",
                    event="completed",
                    created_at=now,
                ).model_dump(mode="json"),
            ],
        }

    return _apply_catalog_node


__all__ = ["WriteToolsProtocol", "make_apply_catalog_node"]
