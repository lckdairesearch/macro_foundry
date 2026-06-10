"""Hello-world LangGraph for onboarding session persistence."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from operator import add
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from macro_foundry.agent.onboarding_state import LLMCallRecord, NodeTransition, RawMessage, TranscriptEntry
from macro_foundry.agent.roles import AgentRole, RoleConfig
from macro_foundry.agent.skills import SkillRegistry

# Type alias for a single-call LLM callable used by research and draft nodes.
# Receives the assembled messages list; returns a dict with content + usage metadata.
LLMCallable = Callable[[list[dict[str, str]]], Awaitable[dict[str, Any]]]


class OnboardingGraphState(TypedDict, total=False):
    """LangGraph state for the onboarding graph."""

    session_metadata: dict[str, Any]
    raw_messages: Annotated[list[dict[str, Any]], add]
    transcript: Annotated[list[dict[str, Any]], add]
    node_transitions: Annotated[list[dict[str, Any]], add]
    llm_calls: Annotated[list[dict[str, Any]], add]
    loaded_skills: Annotated[list[dict[str, Any]], add]
    pending_input: str | None
    # Research outputs
    source_summary: str | None
    existing_catalog_hits: list[dict[str, Any]]
    ambiguity_flags: list[str]
    # Proposal outputs
    proposal: dict[str, Any] | None
    enum_gap_proposals: list[dict[str, Any]]


def _hello_world_node(state: OnboardingGraphState) -> OnboardingGraphState:
    text = state.get("pending_input")
    if not text:
        return {}

    now = datetime.now(timezone.utc)
    response = f"hello-world: {text}"
    return {
        "transcript": [
            TranscriptEntry(role="assistant", text=response, created_at=now).model_dump(mode="json"),
        ],
        "node_transitions": [
            NodeTransition(
                node="hello_world",
                event="responded",
                created_at=now,
            ).model_dump(mode="json"),
        ],
    }


def build_hello_world_graph(checkpointer: Any) -> Any:
    """Compile the minimal onboarding graph with the supplied checkpointer."""

    graph = StateGraph(OnboardingGraphState)
    graph.add_node("hello_world", _hello_world_node)
    graph.add_edge(START, "hello_world")
    graph.add_edge("hello_world", END)
    return graph.compile(checkpointer=checkpointer)


def initial_graph_update(
    *,
    session_metadata: dict[str, Any],
    greeting: str,
) -> OnboardingGraphState:
    """Build the initial checkpoint payload for a new session."""

    now = datetime.now(timezone.utc)
    return {
        "session_metadata": session_metadata,
        "transcript": [
            TranscriptEntry(role="assistant", text=greeting, created_at=now).model_dump(mode="json"),
        ],
        "node_transitions": [
            NodeTransition(
                node="session",
                event="created",
                created_at=now,
            ).model_dump(mode="json"),
        ],
    }


def user_input_graph_update(text: str) -> OnboardingGraphState:
    """Build the checkpoint payload for one operator input."""

    now = datetime.now(timezone.utc)
    return {
        "pending_input": text,
        "raw_messages": [
            RawMessage(role="user", text=text, created_at=now).model_dump(mode="json"),
        ],
        "transcript": [
            TranscriptEntry(role="user", text=text, created_at=now).model_dump(mode="json"),
        ],
    }


def llm_call_graph_update(record: LLMCallRecord) -> OnboardingGraphState:
    """Build a checkpoint payload for one LLM observability record."""

    return {"llm_calls": [record.model_dump(mode="json")]}


def make_research_node(
    llm: LLMCallable,
    role_config: RoleConfig,
    registry: SkillRegistry,
) -> Callable[[OnboardingGraphState], Awaitable[dict[str, Any]]]:
    """Return a research node function that uses the given LLM callable."""

    _ = registry  # skill loading is wired in future slices

    async def _research_node(state: OnboardingGraphState) -> dict[str, Any]:
        intent = state.get("pending_input") or ""
        messages = [{"role": "user", "content": intent}]
        result = await llm(messages)

        now = datetime.now(timezone.utc)
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
            "source_summary": result["source_summary"],
            "existing_catalog_hits": result["existing_catalog_hits"],
            "ambiguity_flags": result["ambiguity_flags"],
            "llm_calls": [llm_record.model_dump(mode="json")],
            "loaded_skills": [],
            "node_transitions": [
                NodeTransition(node="research", event="completed", created_at=now).model_dump(mode="json"),
            ],
        }

    return _research_node


def make_draft_proposal_node(
    llm: LLMCallable,
    role_config: RoleConfig,
    registry: SkillRegistry,
) -> Callable[[OnboardingGraphState], Awaitable[dict[str, Any]]]:
    """Return a draft_proposal node function that uses the given LLM callable."""

    _ = registry  # skill loading is wired in future slices

    async def _draft_proposal_node(state: OnboardingGraphState) -> dict[str, Any]:
        source_summary = state.get("source_summary") or ""
        catalog_hits = state.get("existing_catalog_hits") or []
        messages = [
            {
                "role": "user",
                "content": f"source_summary: {source_summary}\nexisting_catalog_hits: {catalog_hits}",
            }
        ]
        result = await llm(messages)

        now = datetime.now(timezone.utc)
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
            "proposal": result["proposal"],
            "enum_gap_proposals": result.get("enum_gap_proposals", []),
            "llm_calls": [llm_record.model_dump(mode="json")],
            "loaded_skills": [],
            "node_transitions": [
                NodeTransition(node="draft_proposal", event="completed", created_at=now).model_dump(mode="json"),
            ],
        }

    return _draft_proposal_node


def build_research_draft_graph(
    *,
    checkpointer: Any,
    research_llm: LLMCallable,
    draft_llm: LLMCallable,
    role_configs: dict[AgentRole, RoleConfig],
    registry: SkillRegistry,
) -> Any:
    """Compile the research → draft_proposal graph."""

    research_node = make_research_node(research_llm, role_configs[AgentRole.RESEARCHER], registry)
    draft_node = make_draft_proposal_node(draft_llm, role_configs[AgentRole.PROPOSAL_DRAFTER], registry)

    graph = StateGraph(OnboardingGraphState)
    graph.add_node("research", research_node)
    graph.add_node("draft_proposal", draft_node)
    graph.add_edge(START, "research")
    graph.add_edge("research", "draft_proposal")
    graph.add_edge("draft_proposal", END)
    return graph.compile(checkpointer=checkpointer)


__all__ = [
    "LLMCallable",
    "OnboardingGraphState",
    "build_hello_world_graph",
    "build_research_draft_graph",
    "initial_graph_update",
    "llm_call_graph_update",
    "make_draft_proposal_node",
    "make_research_node",
    "user_input_graph_update",
]
