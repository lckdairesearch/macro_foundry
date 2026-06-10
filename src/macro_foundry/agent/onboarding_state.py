"""Pydantic state records for onboarding checkpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, ValidationInfo, model_validator

from macro_foundry.agent.proposal import DraftProposal
from macro_foundry.agent.review import ReviewBundle


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


class LLMCallRecord(BaseModel):
    """Append-only observability record for one LLM call."""

    model_config = ConfigDict(frozen=True)

    role: str
    task_hint: str | None = None
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_estimate_usd: float
    latency_ms: int
    tool_calls: tuple[dict[str, object], ...] = ()
    created_at: datetime


class LoadedSkill(BaseModel):
    """Append-only record of a skill body loaded for an LLM call."""

    model_config = ConfigDict(frozen=True)

    skill_id: str
    trigger_id: str
    node: str
    created_at: datetime
    section_title: str | None = None


class NodeError(BaseModel):
    """Append-only record of a node-level error (retry exhaustion, probe timeout, etc.)."""

    model_config = ConfigDict(frozen=True)

    node: str
    kind: str
    message: str
    created_at: datetime


class EnumGapProposal(BaseModel):
    """Placeholder for slice 14 enum-gap escalation proposal."""

    model_config = ConfigDict(frozen=True)

    column: str
    proposed_value: str
    rationale: str


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
    llm_calls: tuple[LLMCallRecord, ...] = ()
    loaded_skills: tuple[LoadedSkill, ...] = ()
    errors: tuple[NodeError, ...] = ()
    proposal: DraftProposal | None = None
    enum_gap_proposals: tuple[EnumGapProposal, ...] = ()
    # Reviewer fan-out (issue 44)
    extraction_mode: str | None = None
    review_cycle: int = 0
    governance_review: ReviewBundle | None = None
    data_correctness_review: ReviewBundle | None = None

    @property
    def session_cost_usd(self) -> float:
        return sum(r.cost_estimate_usd for r in self.llm_calls)

    @model_validator(mode="after")
    def enforce_checkpoint_invariants(self, info: ValidationInfo) -> "OnboardingCheckpointState":
        if self.proposal is not None and self.enum_gap_proposals:
            raise ValueError("proposal cannot be set while enum_gap_proposals is non-empty")

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
        self._assert_append_only("llm_calls", previous.llm_calls, self.llm_calls)
        self._assert_append_only("loaded_skills", previous.loaded_skills, self.loaded_skills)
        self._assert_append_only("errors", previous.errors, self.errors)
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
    "EnumGapProposal",
    "LLMCallRecord",
    "LoadedSkill",
    "NodeError",
    "NodeTransition",
    "OnboardingCheckpointState",
    "RawMessage",
    "SessionMetadata",
    "TranscriptEntry",
]
