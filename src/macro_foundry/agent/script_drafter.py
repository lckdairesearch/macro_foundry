"""draft_script and validate_script nodes for custom_python onboarding (issue 46)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from macro_foundry.agent.onboarding_state import LLMCallRecord, NodeTransition
from macro_foundry.agent.roles import RoleConfig

# Callable injected into validate_script: (selector_path, probe_payload) -> {"ok": bool}
ProbeCallable = Callable[[str, Any], Awaitable[dict[str, Any]]]

_MAX_DRAFT_CYCLES = 3


def make_draft_script_node(
    llm: Callable[..., Awaitable[dict[str, Any]]],
    role_config: RoleConfig,
    *,
    sandbox_base: Path,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return a draft_script node that writes proposed selectors to the sandbox.

    Only runs when extraction_mode == "custom_python". For any other mode it
    records a skipped transition and returns without calling the LLM or writing
    any files.

    The sandbox path is:  sandbox_base / <session_id> / <selector_name>.py
    Nothing is ever written to src/.
    """

    async def _draft_script_node(state: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)

        if state.get("extraction_mode") != "custom_python":
            return {
                "proposed_selector_path": None,
                "proposed_selector_name": None,
                "node_transitions": [
                    NodeTransition(
                        node="draft_script",
                        event="skipped_config_only",
                        created_at=now,
                    ).model_dump(mode="json")
                ],
            }

        session_id: str = (state.get("session_metadata") or {}).get("session_id", "unknown")
        source_summary: str = state.get("source_summary") or ""
        proposal: dict[str, Any] = state.get("proposal") or {}
        previous_error: str | None = state.get("validation_error")

        content = f"source_summary: {source_summary}\nproposal: {proposal}"
        if previous_error:
            content += f"\nprevious_validation_error: {previous_error}"
        messages = [{"role": "user", "content": content}]

        result = await llm(messages)

        selector_name: str = result["selector_name"]
        selector_code: str = result["selector_code"]

        dest_dir = sandbox_base / session_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{selector_name}.py"
        dest_file.write_text(selector_code, encoding="utf-8")

        llm_record = LLMCallRecord(
            role=role_config.role.value,
            provider=role_config.provider.value,
            model=role_config.default_model,
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            total_tokens=result["total_tokens"],
            cost_estimate_usd=result["cost_estimate_usd"],
            latency_ms=result["latency_ms"],
            created_at=now,
        )

        return {
            "proposed_selector_path": str(dest_file),
            "proposed_selector_name": selector_name,
            "llm_calls": [llm_record.model_dump(mode="json")],
            "loaded_skills": [],
            "node_transitions": [
                NodeTransition(
                    node="draft_script",
                    event="completed",
                    created_at=now,
                ).model_dump(mode="json")
            ],
        }

    return _draft_script_node


def make_validate_script_node(
    *,
    probe_callable: ProbeCallable,
    probe_payload: Any = None,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return a validate_script node that runs the sandbox selector against a probe.

    Writes validation_result ("ok" | "failed") and validation_error to state.
    On failure the conditional edge loops back to draft_script up to
    _MAX_DRAFT_CYCLES times.
    """

    async def _validate_script_node(state: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        selector_path: str | None = state.get("proposed_selector_path")

        if not selector_path:
            return {
                "validation_result": "failed",
                "validation_error": "no proposed_selector_path in state",
                "node_transitions": [
                    NodeTransition(
                        node="validate_script",
                        event="failed",
                        created_at=now,
                    ).model_dump(mode="json")
                ],
            }

        try:
            await probe_callable(selector_path, probe_payload)
        except Exception as exc:
            return {
                "validation_result": "failed",
                "validation_error": str(exc),
                "node_transitions": [
                    NodeTransition(
                        node="validate_script",
                        event="failed",
                        created_at=now,
                    ).model_dump(mode="json")
                ],
            }

        return {
            "validation_result": "ok",
            "validation_error": None,
            "node_transitions": [
                NodeTransition(
                    node="validate_script",
                    event="ok",
                    created_at=now,
                ).model_dump(mode="json")
            ],
        }

    return _validate_script_node


__all__ = [
    "ProbeCallable",
    "make_draft_script_node",
    "make_validate_script_node",
]
