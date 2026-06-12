"""Public onboarding session interface."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from macro_foundry.agent.catalog import WriteToolsProtocol
from macro_foundry.agent.channel import Channel, ChannelEvent, ChannelPrompt, RichQuestionaryChannel
from macro_foundry.agent.checkpoint import postgres_checkpointer_for_target
from macro_foundry.agent.executor import (
    FirstRunLogReaderProtocol,
    FirstRunWriteToolsProtocol,
    OnboardingPackageStoreProtocol,
    TestReviewerProtocol,
)
from macro_foundry.agent.gate import ApprovalLLMCallable, PickerCallable
from macro_foundry.agent.graph import (
    CohortLookupCallable,
    ExtractionModeCallable,
    LLMCallable,
    ReviewerLLMCallable,
    build_onboarding_graph,
    initial_graph_update,
    user_input_graph_update,
)
from macro_foundry.agent.onboarding_state import SessionMetadata
from macro_foundry.agent.roles import AgentRole, RoleOverride, apply_role_overrides, default_role_configs
from macro_foundry.agent.skills import SkillRegistry
from macro_foundry.db import EnvTarget

_log = logging.getLogger(__name__)
_ACTIVE_SESSION_REGISTRY: dict[tuple[int, str], set[str]] = {}


@dataclass(frozen=True)
class SessionRuntimeConfig:
    """Operational defaults for one onboarding session."""

    max_session_cost_usd: float | None = None
    graph_dependencies: OnboardingGraphDependencies | None = None


@dataclass(frozen=True)
class OnboardingGraphDependencies:
    """Injectable external seams for the canonical onboarding graph."""

    research_llm: LLMCallable
    cohort_lookup: CohortLookupCallable
    extraction_mode_classifier: ExtractionModeCallable
    draft_llm: LLMCallable
    governance_llm: ReviewerLLMCallable
    data_correctness_llm: ReviewerLLMCallable
    approval_llm: ApprovalLLMCallable
    gate_1_picker: PickerCallable
    write_tools: WriteToolsProtocol | FirstRunWriteToolsProtocol
    run_logs: FirstRunLogReaderProtocol
    test_reviewer: TestReviewerProtocol
    package_store: OnboardingPackageStoreProtocol
    registry: SkillRegistry
    credential_gap_wait_node: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None


class OnboardingResult(BaseModel):
    """Summary returned after an onboarding CLI session exits."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    saved: bool
    aborted: bool = False
    abort_reason: str | None = None


async def run_onboarding_session(
    *,
    target: EnvTarget,
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
    target: EnvTarget,
    resume_session_id: str | None,
    role_configs: dict[AgentRole, Any],
    channel: Channel | None,
    checkpointer: Any,
    session_id_factory: Callable[[], str] | None,
    runtime_config: SessionRuntimeConfig,
) -> OnboardingResult:
    """Run the onboarding prompt loop against an already-open checkpointer."""

    session_id = resume_session_id or (session_id_factory or _default_session_id)()
    greeting = f"onboarding session {session_id}"
    active_channel = channel or RichQuestionaryChannel()
    dependencies = runtime_config.graph_dependencies or _missing_graph_dependencies()
    graph = build_onboarding_graph(
        checkpointer=checkpointer,
        research_llm=dependencies.research_llm,
        cohort_lookup=dependencies.cohort_lookup,
        extraction_mode_classifier=dependencies.extraction_mode_classifier,
        draft_llm=dependencies.draft_llm,
        governance_llm=dependencies.governance_llm,
        data_correctness_llm=dependencies.data_correctness_llm,
        approval_llm=dependencies.approval_llm,
        gate_1_picker=dependencies.gate_1_picker,
        channel=active_channel,
        write_tools=dependencies.write_tools,
        run_logs=dependencies.run_logs,
        test_reviewer=dependencies.test_reviewer,
        package_store=dependencies.package_store,
        role_configs=role_configs,
        registry=dependencies.registry,
        credential_gap_wait_node=dependencies.credential_gap_wait_node,
    )
    config = {"configurable": {"thread_id": session_id}}

    if resume_session_id is None:
        await _warn_if_concurrent_session(checkpointer, current_session_id=session_id, target=target)

    snapshot = await graph.aget_state(config)
    is_new_session = not snapshot.values
    if is_new_session:
        metadata = SessionMetadata(
            session_id=session_id,
            target_environment=target.value,
            created_at=datetime.now(timezone.utc),
            created_by="macrodb-cli",
            cli_version="0.1.0",
        )
        await graph.aupdate_state(
            config,
            initial_graph_update(
                session_metadata=metadata.model_dump(mode="json"),
                greeting=greeting,
            ),
        )

    if resume_session_id is None:
        _remember_active_session(checkpointer, session_id=session_id, target=target)

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
        package = result.get("onboarding_package") or {}
        if package:
            await active_channel.emit(
                ChannelEvent(
                    text=(
                        f"onboarding_package status={package.get('status')} "
                        f"package_id={package.get('package_id')}"
                    )
                )
            )

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


def _missing_graph_dependencies() -> OnboardingGraphDependencies:
    async def missing_llm(_messages: list[dict[str, str]], **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("onboarding graph dependencies are not configured")

    async def missing_lookup(_catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        raise RuntimeError("onboarding graph dependencies are not configured")

    async def missing_classifier(_source_summary: str) -> str:
        raise RuntimeError("onboarding graph dependencies are not configured")

    async def missing_approval(_state: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("onboarding graph dependencies are not configured")

    async def missing_picker(*_args: Any, **_kwargs: Any) -> str:
        raise RuntimeError("onboarding graph dependencies are not configured")

    class MissingWriteTools:
        async def propose_create_series(self, args: Any) -> dict[str, Any]:
            raise RuntimeError("onboarding graph dependencies are not configured")

        async def record_suggest_human_apply(self, args: Any) -> dict[str, Any]:
            raise RuntimeError("onboarding graph dependencies are not configured")

        async def apply_credential_gap_resolutions(self, args: Any) -> dict[str, Any]:
            raise RuntimeError("onboarding graph dependencies are not configured")

        async def trigger_feed_execution(self, args: Any) -> dict[str, Any]:
            raise RuntimeError("onboarding graph dependencies are not configured")

    class MissingRunLogs:
        async def get_ingestion_run_log(self, run_log_id: str) -> dict[str, Any]:
            raise RuntimeError("onboarding graph dependencies are not configured")

    class MissingPackageStore:
        async def save_onboarding_package(self, package: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("onboarding graph dependencies are not configured")

    return OnboardingGraphDependencies(
        research_llm=missing_llm,
        cohort_lookup=missing_lookup,
        extraction_mode_classifier=missing_classifier,
        draft_llm=missing_llm,
        governance_llm=missing_llm,
        data_correctness_llm=missing_llm,
        approval_llm=missing_approval,
        gate_1_picker=missing_picker,
        write_tools=MissingWriteTools(),
        run_logs=MissingRunLogs(),
        test_reviewer=missing_llm,
        package_store=MissingPackageStore(),
        registry=SkillRegistry({}),
    )


async def _warn_if_concurrent_session(
    checkpointer: Any,
    *,
    current_session_id: str,
    target: EnvTarget,
) -> None:
    registry_key = (id(checkpointer), str(target))
    for thread_id in _ACTIVE_SESSION_REGISTRY.get(registry_key, set()):
        if thread_id != current_session_id:
            _log.warning(
                "concurrent onboarding session detected: %s is already active against %s. "
                "Parallel sessions are unsupported; proceed with caution.",
                thread_id,
                target,
            )
            return

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


def _remember_active_session(checkpointer: Any, *, session_id: str, target: EnvTarget) -> None:
    registry_key = (id(checkpointer), str(target))
    _ACTIVE_SESSION_REGISTRY.setdefault(registry_key, set()).add(session_id)


def _default_session_id() -> str:
    """Generate a human-readable enough local session id."""

    return f"onboard-{uuid4().hex[:12]}"


__all__ = [
    "OnboardingResult",
    "OnboardingGraphDependencies",
    "SessionRuntimeConfig",
    "run_onboarding_session",
]
