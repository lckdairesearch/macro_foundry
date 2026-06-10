"""Post-Gate-1 executor nodes for onboarding sessions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Protocol


class FirstRunWriteToolsProtocol(Protocol):
    """Minimal write-tool surface needed by first-run executor nodes."""

    async def trigger_feed_execution(self, args: Any) -> dict[str, Any]: ...


class FirstRunLogReaderProtocol(Protocol):
    """Read surface for resumable first-run monitoring."""

    async def get_ingestion_run_log(self, run_log_id: str) -> dict[str, Any]: ...


class TestReviewerProtocol(Protocol):
    """LLM reviewer seam for first-run outcome synthesis."""

    async def __call__(self, review_input: dict[str, Any]) -> dict[str, Any]: ...


class OnboardingPackageStoreProtocol(Protocol):
    """Persistence seam for durable test-approved onboarding packages."""

    async def save_onboarding_package(self, package: dict[str, Any]) -> dict[str, Any]: ...


def make_trigger_first_run_node(
    *,
    write_tools: FirstRunWriteToolsProtocol,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return a node that triggers the approved feed exactly once."""

    async def _trigger_first_run_node(state: dict[str, Any]) -> dict[str, Any]:
        from macro_foundry.agent.onboarding_state import NodeTransition
        from macro_foundry.mcp.write_tools import TriggerFeedExecutionArgs

        existing_first_run = state.get("first_run") or {}
        if existing_first_run.get("run_log_id"):
            return {
                "first_run": {
                    **existing_first_run,
                    "triggered": False,
                },
            }

        if not state.get("gate_1_applied"):
            raise RuntimeError("trigger_first_run requires gate_1_applied=True")

        applied_catalog = state.get("applied_catalog") or {}
        feed_id = applied_catalog.get("feed_id") or state.get("first_run_feed_id")
        if not feed_id:
            raise RuntimeError("trigger_first_run requires an applied catalog feed_id")

        result = await write_tools.trigger_feed_execution(TriggerFeedExecutionArgs(feed_id=feed_id))
        now = datetime.now(timezone.utc)
        return {
            "first_run": {
                "feed_id": result.get("feed_id", str(feed_id)),
                "run_log_id": result["run_log_id"],
                "status": result.get("status"),
                "triggered": True,
            },
            "node_transitions": [
                NodeTransition(
                    node="trigger_first_run",
                    event="completed",
                    created_at=now,
                ).model_dump(mode="json"),
            ],
        }

    return _trigger_first_run_node


def make_monitor_first_run_node(
    *,
    run_logs: FirstRunLogReaderProtocol,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return a node that refreshes first-run status from the persisted run log."""

    async def _monitor_first_run_node(state: dict[str, Any]) -> dict[str, Any]:
        from macro_foundry.agent.onboarding_state import NodeTransition

        first_run = state.get("first_run") or {}
        run_log_id = first_run.get("run_log_id")
        if not run_log_id:
            raise RuntimeError("monitor_first_run requires first_run.run_log_id")

        refreshed = await run_logs.get_ingestion_run_log(run_log_id)
        now = datetime.now(timezone.utc)
        return {
            "first_run": {
                **first_run,
                **refreshed,
                "terminal": refreshed.get("status") in {"success", "failed", "partial"},
            },
            "node_transitions": [
                NodeTransition(
                    node="monitor_first_run",
                    event="completed",
                    created_at=now,
                ).model_dump(mode="json"),
            ],
        }

    return _monitor_first_run_node


def make_test_review_node(
    *,
    reviewer: TestReviewerProtocol,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return a node that classifies and summarizes first-run trustworthiness."""

    async def _test_review_node(state: dict[str, Any]) -> dict[str, Any]:
        from macro_foundry.agent.onboarding_state import NodeTransition

        first_run = state.get("first_run") or {}
        if not first_run:
            raise RuntimeError("test_review requires first_run state")

        tolerated_warnings = list(first_run.get("warnings") or [])
        hard_failures = _hard_failures_for_first_run(first_run)
        if hard_failures:
            status = "failed"
        elif tolerated_warnings:
            status = "passed_with_warnings"
        else:
            status = "passed"

        synthesis = await reviewer(
            {
                "first_run": first_run,
                "status": status,
                "tolerated_warnings": tolerated_warnings,
                "hard_failures": hard_failures,
            }
        )

        now = datetime.now(timezone.utc)
        return {
            "test_review": {
                "status": status,
                "summary": synthesis.get("summary", ""),
                "tolerated_warnings": tolerated_warnings,
                "hard_failures": hard_failures,
            },
            "node_transitions": [
                NodeTransition(
                    node="test_review",
                    event="completed",
                    created_at=now,
                ).model_dump(mode="json"),
            ],
        }

    return _test_review_node


def _hard_failures_for_first_run(first_run: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    status = first_run.get("status")
    diagnostics = first_run.get("diagnostics") or {}
    error_text = str(first_run.get("error_message") or "").lower()
    diagnostic_outcome = str(diagnostics.get("outcome") or "").lower()

    if status == "failed":
        failures.append("run status failed")
    if diagnostic_outcome in {"config_error", "provider_error"}:
        failures.append("auth/config/runtime error")
    if any(token in error_text for token in ("auth", "401", "403", "config", "runtime")):
        if "auth/config/runtime error" not in failures:
            failures.append("auth/config/runtime error")
    if any(token in error_text for token in ("wrong canonical", "identity", "materially disagree")):
        failures.append("canonical identity disagreement")
    if any(token in error_text for token in ("period bound", "period bounds", "parse")):
        failures.append("untrustworthy period-bound parsing")
    return failures


def make_emit_package_node(
    *,
    package_store: OnboardingPackageStoreProtocol,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return a node that persists the test-approved onboarding package."""

    async def _emit_package_node(state: dict[str, Any]) -> dict[str, Any]:
        from macro_foundry.agent.onboarding_state import NodeTransition

        test_review = state.get("test_review") or {}
        if test_review.get("status") == "failed":
            raise RuntimeError("emit_package refuses failed test_review state")

        session_metadata = state.get("session_metadata") or {}
        applied_catalog = state.get("applied_catalog") or {}
        first_run = state.get("first_run") or {}
        warnings = list(test_review.get("tolerated_warnings") or first_run.get("warnings") or [])
        package = {
            "status": "test-approved",
            "proposal_summary": state.get("proposal") or {},
            "canonical_rows": applied_catalog,
            "reviewer_findings": {
                "governance": state.get("governance_review"),
                "data_correctness": state.get("data_correctness_review"),
            },
            "first_run_summary": first_run,
            "warnings": warnings,
            "thread_id": session_metadata.get("session_id"),
            "change_proposal_id": applied_catalog.get("proposal_id")
            or applied_catalog.get("change_proposal_id"),
        }
        result = await package_store.save_onboarding_package(package)
        now = datetime.now(timezone.utc)
        return {
            "onboarding_package": {
                **result,
                "status": "test-approved",
            },
            "node_transitions": [
                NodeTransition(
                    node="emit_package",
                    event="completed",
                    created_at=now,
                ).model_dump(mode="json"),
            ],
        }

    return _emit_package_node


__all__ = [
    "FirstRunLogReaderProtocol",
    "FirstRunWriteToolsProtocol",
    "OnboardingPackageStoreProtocol",
    "TestReviewerProtocol",
    "make_emit_package_node",
    "make_monitor_first_run_node",
    "make_test_review_node",
    "make_trigger_first_run_node",
]
