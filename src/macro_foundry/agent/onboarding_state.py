"""Pydantic state records for onboarding checkpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, ValidationInfo, model_validator


class SessionMetadata(BaseModel):
    """Immutable metadata locked when an onboarding session is created."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    target_environment: str
    created_at: datetime
    created_by: str
    cli_version: str


class RawMessage(BaseModel):
    """Append-only raw operator/agent message record."""

    model_config = ConfigDict(frozen=True)

    role: str
    text: str
    created_at: datetime


class TranscriptEntry(BaseModel):
    """Append-only human-readable transcript entry."""

    model_config = ConfigDict(frozen=True)

    role: str
    text: str
    created_at: datetime


class NodeTransition(BaseModel):
    """Append-only graph transition record."""

    model_config = ConfigDict(frozen=True)

    node: str
    event: str
    created_at: datetime


class LoadedSkill(BaseModel):
    """Append-only record of a skill body loaded for an LLM call."""

    model_config = ConfigDict(frozen=True)

    skill_id: str
    trigger_id: str
    node: str
    created_at: datetime
    section_title: str | None = None


class OnboardingCheckpointState(BaseModel):
    """Validated onboarding checkpoint state.

    When a previous state is supplied in Pydantic validation context under
    ``previous_state``, append-only collections must preserve that previous
    state as an exact prefix.
    """

    model_config = ConfigDict(frozen=True)

    session_metadata: SessionMetadata
    raw_messages: tuple[RawMessage, ...] = ()
    transcript: tuple[TranscriptEntry, ...] = ()
    node_transitions: tuple[NodeTransition, ...] = ()
    loaded_skills: tuple[LoadedSkill, ...] = ()

    @model_validator(mode="after")
    def enforce_checkpoint_invariants(self, info: ValidationInfo) -> "OnboardingCheckpointState":
        previous = None
        if isinstance(info.context, dict):
            previous = info.context.get("previous_state")
        if previous is None:
            return self
        if not isinstance(previous, OnboardingCheckpointState):
            raise ValueError("previous_state must be an OnboardingCheckpointState")
        if self.session_metadata != previous.session_metadata:
            raise ValueError("session_metadata is immutable")
        self._assert_append_only("raw_messages", previous.raw_messages, self.raw_messages)
        self._assert_append_only("transcript", previous.transcript, self.transcript)
        self._assert_append_only("node_transitions", previous.node_transitions, self.node_transitions)
        self._assert_append_only("loaded_skills", previous.loaded_skills, self.loaded_skills)
        return self

    @staticmethod
    def _assert_append_only(
        field_name: str,
        previous: tuple[BaseModel, ...],
        current: tuple[BaseModel, ...],
    ) -> None:
        if len(current) < len(previous) or current[: len(previous)] != previous:
            raise ValueError(f"{field_name} is append-only")


__all__ = [
    "NodeTransition",
    "LoadedSkill",
    "OnboardingCheckpointState",
    "RawMessage",
    "SessionMetadata",
    "TranscriptEntry",
]
