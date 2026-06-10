"""Public onboarding session interface."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from macro_foundry.agent.channel import Channel, ChannelEvent, ChannelPrompt, RichQuestionaryChannel
from macro_foundry.agent.checkpoint import postgres_checkpointer_for_target
from macro_foundry.agent.graph import build_hello_world_graph, initial_graph_update, user_input_graph_update
from macro_foundry.agent.onboarding_state import SessionMetadata
from macro_foundry.agent.onboarding_targets import OnboardingTarget
from macro_foundry.agent.roles import AgentRole, RoleOverride, apply_role_overrides, default_role_configs


class OnboardingResult(BaseModel):
    """Summary returned after an onboarding CLI session exits."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    saved: bool


async def run_onboarding_session(
    *,
    target: OnboardingTarget,
    resume_session_id: str | None,
    role_config_overrides: dict[AgentRole, RoleOverride] | None = None,
    channel: Channel | None = None,
    checkpointer: Any | None = None,
    session_id_factory: Callable[[], str] | None = None,
) -> OnboardingResult:
    """Run the onboarding session shell."""

    role_configs = apply_role_overrides(default_role_configs(), role_config_overrides or {})

    if checkpointer is None:
        async with postgres_checkpointer_for_target(target) as postgres_checkpointer:
            return await _run_onboarding_loop(
                target=target,
                resume_session_id=resume_session_id,
                role_configs=role_configs,
                channel=channel,
                checkpointer=postgres_checkpointer,
                session_id_factory=session_id_factory,
            )

    return await _run_onboarding_loop(
        target=target,
        resume_session_id=resume_session_id,
        role_configs=role_configs,
        channel=channel,
        checkpointer=checkpointer,
        session_id_factory=session_id_factory,
    )


async def _run_onboarding_loop(
    *,
    target: OnboardingTarget,
    resume_session_id: str | None,
    role_configs: dict[AgentRole, object],
    channel: Channel | None,
    checkpointer: Any,
    session_id_factory: Callable[[], str] | None,
) -> OnboardingResult:
    """Run the onboarding prompt loop against an already-open checkpointer."""

    _ = role_configs
    session_id = resume_session_id or (session_id_factory or _default_session_id)()
    greeting = f"hello-world onboarding session {session_id}"
    active_channel = channel or RichQuestionaryChannel()
    graph = build_hello_world_graph(checkpointer)
    config = {"configurable": {"thread_id": session_id}}

    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        metadata = SessionMetadata(
            session_id=session_id,
            target_environment=target,
            created_at=datetime.now(timezone.utc),
            created_by="macrodb-cli",
            cli_version="0.1.0",
        )
        await graph.ainvoke(
            initial_graph_update(
                session_metadata=metadata.model_dump(mode="json"),
                greeting=greeting,
            ),
            config,
        )

    snapshot = await graph.aget_state(config)
    for entry in snapshot.values.get("transcript", []):
        if entry["role"] == "assistant":
            await active_channel.emit(ChannelEvent(text=entry["text"]))

    while True:
        response = await active_channel.prompt(ChannelPrompt(text="> "))
        text = response.text.strip()
        if text in {"/save", ""}:
            await active_channel.emit(ChannelEvent(text=f"session {session_id} saved"))
            return OnboardingResult(session_id=session_id, saved=True)
        result = await graph.ainvoke(user_input_graph_update(text), config)
        transcript = result.get("transcript", [])
        if transcript:
            await active_channel.emit(ChannelEvent(text=transcript[-1]["text"]))


def _default_session_id() -> str:
    """Generate a human-readable enough local session id."""

    return f"onboard-{uuid4().hex[:12]}"


__all__ = [
    "OnboardingResult",
    "OnboardingTarget",
    "run_onboarding_session",
]
