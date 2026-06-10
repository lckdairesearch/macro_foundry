"""Hello-world LangGraph for onboarding session persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from operator import add
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from macro_foundry.agent.onboarding_state import LLMCallRecord, NodeTransition, RawMessage, TranscriptEntry


class OnboardingGraphState(TypedDict, total=False):
    """LangGraph state for the issue-34 hello-world slice."""

    session_metadata: dict[str, Any]
    raw_messages: Annotated[list[dict[str, Any]], add]
    transcript: Annotated[list[dict[str, Any]], add]
    node_transitions: Annotated[list[dict[str, Any]], add]
    llm_calls: Annotated[list[dict[str, Any]], add]
    pending_input: str | None


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


__all__ = [
    "OnboardingGraphState",
    "build_hello_world_graph",
    "initial_graph_update",
    "llm_call_graph_update",
    "user_input_graph_update",
]
