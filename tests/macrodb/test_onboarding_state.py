"""State schema coverage for onboarding checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from macro_foundry.agent.onboarding import OnboardingTarget
from macro_foundry.agent.onboarding_state import (
    LoadedSkill,
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
