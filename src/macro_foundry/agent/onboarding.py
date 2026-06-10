"""Public onboarding session interface."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
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

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionRuntimeConfig:
    """Operational defaults for one onboarding session."""

    max_session_cost_usd: float | None = None


class OnboardingResult(BaseModel):
    """Summary returned after an onboarding CLI session exits."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    saved: bool
    aborted: bool = False
    abort_reason: str | None = None


async def run_onboarding_session(
    *,
    target: OnboardingTarget,
    resume_session_id: str | None,
    role_config_overrides: dict[AgentRole, RoleOverride] | None = None,
    channel: Channel | None = None,
    checkpointer: Any | None = None,
    session_id_factory: Callable[[], str] | None = None,
    runtime_config: SessionRuntimeConfig | None = None,
) -> OnboardingResult:
    """Run the onboarding session shell."""

    role_configs = apply_role_overrides(default_role_configs(), role_config_overrides or {})
    effective_runtime = runtime_config or SessionRuntimeConfig()

    if checkpointer is None:
        async with postgres_checkpointer_for_target(target) as postgres_checkpointer:
            return await _run_onboarding_loop(
                target=target,
                resume_session_id=resume_session_id,
                role_configs=role_configs,
                channel=channel,
                checkpointer=postgres_checkpointer,
                session_id_factory=session_id_factory,
                runtime_config=effective_runtime,
            )

    return await _run_onboarding_loop(
        target=target,
        resume_session_id=resume_session_id,
        role_configs=role_configs,
        channel=channel,
        checkpointer=checkpointer,
        session_id_factory=session_id_factory,
        runtime_config=effective_runtime,
    )


async def _run_onboarding_loop(
    *,
    target: OnboardingTarget,
    resume_session_id: str | None,
    role_configs: dict[AgentRole, object],
    channel: Channel | None,
    checkpointer: Any,
    session_id_factory: Callable[[], str] | None,
    runtime_config: SessionRuntimeConfig,
) -> OnboardingResult:
    """Run the onboarding prompt loop against an already-open checkpointer."""

    _ = role_configs
    session_id = resume_session_id or (session_id_factory or _default_session_id)()
    greeting = f"hello-world onboarding session {session_id}"
    active_channel = channel or RichQuestionaryChannel()
    graph = build_hello_world_graph(checkpointer)
    config = {"configurable": {"thread_id": session_id}}

    snapshot = await graph.aget_state(config)
    is_new_session = not snapshot.values
    if is_new_session:
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
        await _warn_if_concurrent_session(checkpointer, current_session_id=session_id, target=target)

    if _cost_cap_exceeded(runtime_config, session_cost_usd=0.0):
        return OnboardingResult(
            session_id=session_id,
            saved=True,
            aborted=True,
            abort_reason="cost_cap_exceeded",
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

        session_cost = sum(r.get("cost_estimate_usd", 0.0) for r in result.get("llm_calls", []))
        if _cost_cap_exceeded(runtime_config, session_cost_usd=session_cost):
            return OnboardingResult(
                session_id=session_id,
                saved=True,
                aborted=True,
                abort_reason="cost_cap_exceeded",
            )


def _cost_cap_exceeded(runtime_config: SessionRuntimeConfig, *, session_cost_usd: float) -> bool:
    if runtime_config.max_session_cost_usd is None:
        return False
    return session_cost_usd >= runtime_config.max_session_cost_usd


async def _warn_if_concurrent_session(
    checkpointer: Any,
    *,
    current_session_id: str,
    target: OnboardingTarget,
) -> None:
    try:
        async for config_entry in checkpointer.alist({}):
            thread_id = config_entry.config.get("configurable", {}).get("thread_id", "")
            if thread_id and thread_id != current_session_id:
                _log.warning(
                    "concurrent onboarding session detected: %s is already active against %s. "
                    "Parallel sessions are unsupported; proceed with caution.",
                    thread_id,
                    target,
                )
                break
    except Exception:
        pass


def _default_session_id() -> str:
    """Generate a human-readable enough local session id."""

    return f"onboard-{uuid4().hex[:12]}"


__all__ = [
    "OnboardingResult",
    "OnboardingTarget",
    "SessionRuntimeConfig",
    "run_onboarding_session",
]
