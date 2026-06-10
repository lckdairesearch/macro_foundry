"""Tests for post-Gate-1 executor nodes (issue 50)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from macro_foundry.agent.executor import (
    make_emit_package_node,
    make_monitor_first_run_node,
    make_test_review_node,
    make_trigger_first_run_node,
)
from macro_foundry.agent.onboarding_state import OnboardingCheckpointState


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_trigger_first_run_is_idempotent_on_resume() -> None:
    write_tools = AsyncMock()
    write_tools.trigger_feed_execution.return_value = {
        "feed_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "run_log_id": "bbbbbbbb-0000-0000-0000-000000000001",
        "status": "success",
    }
    node = make_trigger_first_run_node(write_tools=write_tools)

    state: dict[str, Any] = {
        "gate_1_applied": True,
        "applied_catalog": {"feed_id": "aaaaaaaa-0000-0000-0000-000000000001"},
    }

    first_result = await node(state)
    resumed_result = await node(state | first_result)

    write_tools.trigger_feed_execution.assert_called_once()
    assert first_result["first_run"]["run_log_id"] == "bbbbbbbb-0000-0000-0000-000000000001"
    assert resumed_result["first_run"]["run_log_id"] == "bbbbbbbb-0000-0000-0000-000000000001"
    assert resumed_result["first_run"]["triggered"] is False


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_monitor_first_run_requeries_run_log_on_resume() -> None:
    run_logs = AsyncMock()
    run_logs.get_ingestion_run_log.return_value = {
        "run_log_id": "bbbbbbbb-0000-0000-0000-000000000001",
        "status": "success",
        "rows_fetched": 12,
        "rows_inserted": 10,
        "rows_skipped": 2,
        "warnings": ["requested start date predates provider coverage"],
    }
    node = make_monitor_first_run_node(run_logs=run_logs)

    state: dict[str, Any] = {
        "first_run": {
            "run_log_id": "bbbbbbbb-0000-0000-0000-000000000001",
            "status": "partial",
        },
    }

    result = await node(state)

    run_logs.get_ingestion_run_log.assert_called_once_with("bbbbbbbb-0000-0000-0000-000000000001")
    assert result["first_run"]["status"] == "success"
    assert result["first_run"]["rows_inserted"] == 10
    assert result["first_run"]["terminal"] is True


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_review_distinguishes_tolerated_warnings_from_hard_failures() -> None:
    reviewer = AsyncMock()
    reviewer.side_effect = [
        {"summary": "Backfill succeeded from the provider's first available period."},
        {"summary": "Auth failure makes the first-run result untrustworthy."},
    ]
    node = make_test_review_node(reviewer=reviewer)

    warning_result = await node(
        {
            "first_run": {
                "status": "success",
                "warnings": ["requested start date predates provider coverage"],
                "rows_inserted": 10,
            },
        }
    )
    failure_result = await node(
        {
            "first_run": {
                "status": "failed",
                "error_message": "401 auth error",
                "diagnostics": {"outcome": "config_error"},
            },
        }
    )

    assert warning_result["test_review"]["status"] == "passed_with_warnings"
    assert warning_result["test_review"]["tolerated_warnings"] == [
        "requested start date predates provider coverage"
    ]
    assert warning_result["test_review"]["hard_failures"] == []
    assert failure_result["test_review"]["status"] == "failed"
    assert "auth/config/runtime error" in failure_result["test_review"]["hard_failures"]


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_emit_package_persists_test_approved_artifact_with_back_references() -> None:
    package_store = AsyncMock()
    package_store.save_onboarding_package.return_value = {
        "package_id": "cccccccc-0000-0000-0000-000000000001",
    }
    node = make_emit_package_node(package_store=package_store)

    result = await node(
        {
            "session_metadata": {"session_id": "thread-123"},
            "proposal": {"series": {"code": "CPI_HKG_TOTAL_M"}},
            "applied_catalog": {
                "proposal_id": "dddddddd-0000-0000-0000-000000000001",
                "series_id": "eeeeeeee-0000-0000-0000-000000000001",
                "feed_id": "aaaaaaaa-0000-0000-0000-000000000001",
            },
            "governance_review": {"findings": ["governance ok"]},
            "data_correctness_review": {"findings": ["data ok"]},
            "first_run": {
                "run_log_id": "bbbbbbbb-0000-0000-0000-000000000001",
                "status": "success",
                "rows_inserted": 10,
                "warnings": ["requested start date predates provider coverage"],
            },
            "test_review": {
                "status": "passed_with_warnings",
                "summary": "First run is acceptable with coverage warning.",
                "tolerated_warnings": ["requested start date predates provider coverage"],
                "hard_failures": [],
            },
        }
    )

    package_store.save_onboarding_package.assert_called_once()
    package = package_store.save_onboarding_package.call_args.args[0]
    assert package["status"] == "test-approved"
    assert package["thread_id"] == "thread-123"
    assert package["change_proposal_id"] == "dddddddd-0000-0000-0000-000000000001"
    assert package["canonical_rows"]["series_id"] == "eeeeeeee-0000-0000-0000-000000000001"
    assert package["warnings"] == ["requested start date predates provider coverage"]
    assert result["onboarding_package"]["package_id"] == "cccccccc-0000-0000-0000-000000000001"


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_executor_state_is_recoverable_between_nodes() -> None:
    write_tools = AsyncMock()
    write_tools.trigger_feed_execution.return_value = {
        "feed_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "run_log_id": "bbbbbbbb-0000-0000-0000-000000000001",
        "status": "success",
    }
    run_logs = AsyncMock()
    run_logs.get_ingestion_run_log.return_value = {
        "run_log_id": "bbbbbbbb-0000-0000-0000-000000000001",
        "status": "success",
        "rows_inserted": 10,
        "warnings": [],
    }
    reviewer = AsyncMock(return_value={"summary": "First run passed."})
    package_store = AsyncMock()
    package_store.save_onboarding_package.return_value = {
        "package_id": "cccccccc-0000-0000-0000-000000000001"
    }

    state: dict[str, Any] = {
        "session_metadata": {
            "session_id": "thread-123",
            "target_environment": "staging",
            "created_at": "2026-06-10T00:00:00Z",
            "created_by": "macrodb-cli",
            "cli_version": "0.1.0",
        },
        "gate_1_applied": True,
        "applied_catalog": {
            "proposal_id": "dddddddd-0000-0000-0000-000000000001",
            "feed_id": "aaaaaaaa-0000-0000-0000-000000000001",
        },
    }

    for node in (
        make_trigger_first_run_node(write_tools=write_tools),
        make_monitor_first_run_node(run_logs=run_logs),
        make_test_review_node(reviewer=reviewer),
        make_emit_package_node(package_store=package_store),
    ):
        state.update(await node(state))
        OnboardingCheckpointState.model_validate(state)

    assert state["onboarding_package"]["status"] == "test-approved"
