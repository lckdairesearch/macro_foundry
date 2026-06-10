"""State schema coverage for onboarding checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from macro_foundry.agent.onboarding import OnboardingTarget
from macro_foundry.agent.onboarding_state import (
    LLMCallRecord,
    LoadedSkill,
    NodeError,
    NodeTransition,
    OnboardingCheckpointState,
    RawMessage,
    SessionMetadata,
    TranscriptEntry,
)


@pytest.mark.no_db
def test_onboarding_checkpoint_state_enforces_append_only_fields() -> None:
    created_at = datetime(2026, 6, 10, tzinfo=timezone.utc)
    metadata = SessionMetadata(
        session_id="friendly-session",
        target_environment=OnboardingTarget.DEV.value,
        created_at=created_at,
        created_by="macrodb-cli",
        cli_version="0.1.0",
    )
    base = OnboardingCheckpointState(
        session_metadata=metadata,
        raw_messages=(RawMessage(role="user", text="hello", created_at=created_at),),
        transcript=(TranscriptEntry(role="user", text="hello", created_at=created_at),),
        node_transitions=(NodeTransition(node="hello_world", event="responded", created_at=created_at),),
        loaded_skills=(
            LoadedSkill(
                skill_id="skill-one",
                trigger_id="trigger-one",
                node="draft_proposal",
                created_at=created_at,
            ),
        ),
    )

    appended = OnboardingCheckpointState.model_validate(
        {
            "session_metadata": metadata.model_dump(),
            "raw_messages": [
                RawMessage(role="user", text="hello", created_at=created_at).model_dump(),
                RawMessage(role="user", text="again", created_at=created_at).model_dump(),
            ],
            "transcript": [
                TranscriptEntry(role="user", text="hello", created_at=created_at).model_dump(),
                TranscriptEntry(role="user", text="again", created_at=created_at).model_dump(),
            ],
            "node_transitions": [
                NodeTransition(node="hello_world", event="responded", created_at=created_at).model_dump(),
                NodeTransition(node="hello_world", event="responded", created_at=created_at).model_dump(),
            ],
            "loaded_skills": [
                LoadedSkill(
                    skill_id="skill-one",
                    trigger_id="trigger-one",
                    node="draft_proposal",
                    created_at=created_at,
                ).model_dump(),
                LoadedSkill(
                    skill_id="skill-two",
                    trigger_id="trigger-two",
                    node="governance_review",
                    created_at=created_at,
                ).model_dump(),
            ],
        },
        context={"previous_state": base},
    )

    assert len(appended.raw_messages) == 2

    with pytest.raises(ValidationError, match="raw_messages is append-only"):
        OnboardingCheckpointState.model_validate(
            {
                "session_metadata": metadata.model_dump(),
                "raw_messages": [],
                "transcript": [entry.model_dump() for entry in base.transcript],
                "node_transitions": [entry.model_dump() for entry in base.node_transitions],
            },
            context={"previous_state": base},
        )

    changed_metadata = metadata.model_copy(update={"target_environment": OnboardingTarget.STAGING.value})
    with pytest.raises(ValidationError, match="session_metadata is immutable"):
        OnboardingCheckpointState.model_validate(
            {
                "session_metadata": changed_metadata.model_dump(),
                "raw_messages": [entry.model_dump() for entry in base.raw_messages],
                "transcript": [entry.model_dump() for entry in base.transcript],
                "node_transitions": [entry.model_dump() for entry in base.node_transitions],
                "loaded_skills": [entry.model_dump() for entry in base.loaded_skills],
            },
            context={"previous_state": base},
        )

    with pytest.raises(ValidationError, match="loaded_skills is append-only"):
        OnboardingCheckpointState.model_validate(
            {
                "session_metadata": metadata.model_dump(),
                "raw_messages": [entry.model_dump() for entry in base.raw_messages],
                "transcript": [entry.model_dump() for entry in base.transcript],
                "node_transitions": [entry.model_dump() for entry in base.node_transitions],
                "loaded_skills": [],
            },
            context={"previous_state": base},
        )


@pytest.mark.no_db
def test_onboarding_checkpoint_state_records_llm_calls() -> None:
    created_at = datetime(2026, 6, 10, tzinfo=timezone.utc)
    metadata = SessionMetadata(
        session_id="friendly-session",
        target_environment=OnboardingTarget.DEV.value,
        created_at=created_at,
        created_by="macrodb-cli",
        cli_version="0.1.0",
    )

    state = OnboardingCheckpointState(
        session_metadata=metadata,
        llm_calls=(
            LLMCallRecord(
                role="researcher",
                task_hint="provider_scan",
                provider="openai",
                model="gpt-5.1",
                prompt_tokens=120,
                completion_tokens=32,
                total_tokens=152,
                cost_estimate_usd=0.0042,
                latency_ms=875,
                tool_calls=({"name": "lookup_concept", "arguments": {"code": "CPI"}},),
                created_at=created_at,
            ),
        ),
    )

    assert state.llm_calls[0].model == "gpt-5.1"
    assert state.llm_calls[0].tool_calls == ({"name": "lookup_concept", "arguments": {"code": "CPI"}},)


@pytest.mark.no_db
def test_session_cost_usd_sums_llm_call_estimates() -> None:
    created_at = datetime(2026, 6, 10, tzinfo=timezone.utc)
    metadata = SessionMetadata(
        session_id="s1",
        target_environment="dev",
        created_at=created_at,
        created_by="macrodb-cli",
        cli_version="0.1.0",
    )

    def _call(cost: float) -> LLMCallRecord:
        return LLMCallRecord(
            role="researcher",
            provider="openai",
            model="gpt-5.1",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            cost_estimate_usd=cost,
            latency_ms=100,
            created_at=created_at,
        )

    state = OnboardingCheckpointState(
        session_metadata=metadata,
        llm_calls=(_call(0.01), _call(0.02), _call(0.03)),
    )

    assert state.session_cost_usd == pytest.approx(0.06)


@pytest.mark.no_db
def test_session_cost_usd_is_zero_with_no_calls() -> None:
    created_at = datetime(2026, 6, 10, tzinfo=timezone.utc)
    metadata = SessionMetadata(
        session_id="s2",
        target_environment="dev",
        created_at=created_at,
        created_by="macrodb-cli",
        cli_version="0.1.0",
    )
    state = OnboardingCheckpointState(session_metadata=metadata)
    assert state.session_cost_usd == 0.0


@pytest.mark.no_db
def test_onboarding_checkpoint_state_carries_first_run_executor_artifacts() -> None:
    created_at = datetime(2026, 6, 10, tzinfo=timezone.utc)
    metadata = SessionMetadata(
        session_id="s-first-run",
        target_environment="staging",
        created_at=created_at,
        created_by="macrodb-cli",
        cli_version="0.1.0",
    )

    state = OnboardingCheckpointState(
        session_metadata=metadata,
        applied_catalog={
            "proposal_id": "aaaaaaaa-0000-0000-0000-000000000001",
            "feed_id": "bbbbbbbb-0000-0000-0000-000000000001",
        },
        first_run={
            "run_log_id": "cccccccc-0000-0000-0000-000000000001",
            "status": "success",
            "rows_inserted": 10,
        },
        test_review={
            "status": "passed_with_warnings",
            "summary": "acceptable",
            "tolerated_warnings": ["requested start date predates provider coverage"],
            "hard_failures": [],
        },
        onboarding_package={
            "package_id": "dddddddd-0000-0000-0000-000000000001",
            "status": "test-approved",
        },
    )

    assert state.applied_catalog["feed_id"] == "bbbbbbbb-0000-0000-0000-000000000001"
    assert state.first_run["run_log_id"] == "cccccccc-0000-0000-0000-000000000001"
    assert state.test_review["status"] == "passed_with_warnings"
    assert state.onboarding_package["status"] == "test-approved"


@pytest.mark.no_db
def test_node_error_is_append_only_on_checkpoint_state() -> None:
    created_at = datetime(2026, 6, 10, tzinfo=timezone.utc)
    metadata = SessionMetadata(
        session_id="s3",
        target_environment="dev",
        created_at=created_at,
        created_by="macrodb-cli",
        cli_version="0.1.0",
    )
    base = OnboardingCheckpointState(
        session_metadata=metadata,
        errors=(NodeError(node="research", kind="probe_timeout", message="30s exceeded", created_at=created_at),),
    )

    appended = OnboardingCheckpointState.model_validate(
        {
            "session_metadata": metadata.model_dump(),
            "errors": [
                NodeError(node="research", kind="probe_timeout", message="30s exceeded", created_at=created_at).model_dump(),
                NodeError(node="research", kind="retry_exhausted", message="3 retries failed", created_at=created_at).model_dump(),
            ],
        },
        context={"previous_state": base},
    )
    assert len(appended.errors) == 2

    with pytest.raises(ValidationError, match="errors is append-only"):
        OnboardingCheckpointState.model_validate(
            {"session_metadata": metadata.model_dump(), "errors": []},
            context={"previous_state": base},
        )
