"""LangGraph definitions for onboarding session persistence."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from operator import add
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from macro_foundry.agent.onboarding_state import LLMCallRecord, NodeTransition, RawMessage, TranscriptEntry
from macro_foundry.agent.proposal import HarmonisationItem, ReferenceMetadata
from macro_foundry.agent.roles import AgentRole, RoleConfig
from macro_foundry.agent.skills import SkillRegistry

# Type alias for a single-call LLM callable used by research and draft nodes.
# Receives the assembled messages list; returns a dict with content + usage metadata.
LLMCallable = Callable[[list[dict[str, str]]], Awaitable[dict[str, Any]]]

# Callable that takes existing_catalog_hits and returns {cohort_a, cohort_b, cohort_c}.
CohortLookupCallable = Callable[[list[dict[str, Any]]], Awaitable[dict[str, Any]]]

# Callable that takes source_summary and returns "config_only" | "custom_python".
ExtractionModeCallable = Callable[[str], Awaitable[str]]


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
    # Reference metadata (gather_reference_metadata node)
    reference_metadata: dict[str, Any] | None
    is_first_in_family: bool | None
    # Extraction mode (classify_extraction_mode node)
    extraction_mode: str | None
    # Proposal outputs
    proposal: dict[str, Any] | None
    enum_gap_proposals: list[dict[str, Any]]
    harmonisation_items: list[dict[str, Any]]
    suggest_human_apply: list[dict[str, Any]]


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


def make_gather_reference_metadata_node(
    cohort_lookup: CohortLookupCallable,
) -> Callable[[OnboardingGraphState], Awaitable[dict[str, Any]]]:
    """Return a gather_reference_metadata node that calls the cohort lookup callable."""

    async def _gather_node(state: OnboardingGraphState) -> dict[str, Any]:
        catalog_hits = state.get("existing_catalog_hits") or []
        cohorts = await cohort_lookup(catalog_hits)

        is_first = len(cohorts.get("cohort_a") or []) == 0
        meta = ReferenceMetadata(
            cohort_a=cohorts.get("cohort_a") or [],
            cohort_b=cohorts.get("cohort_b") or [],
            cohort_c=cohorts.get("cohort_c") or [],
            is_first_in_family=is_first,
        )

        now = datetime.now(timezone.utc)
        return {
            "reference_metadata": meta.model_dump(mode="json"),
            "is_first_in_family": is_first,
            "node_transitions": [
                NodeTransition(
                    node="gather_reference_metadata",
                    event="completed",
                    created_at=now,
                ).model_dump(mode="json"),
            ],
        }

    return _gather_node


def make_classify_extraction_mode_node(
    classifier: ExtractionModeCallable,
) -> Callable[[OnboardingGraphState], Awaitable[dict[str, Any]]]:
    """Return a classify_extraction_mode node that writes extraction_mode to state."""

    async def _classify_node(state: OnboardingGraphState) -> dict[str, Any]:
        source_summary = state.get("source_summary") or ""
        extraction_mode = await classifier(source_summary)

        now = datetime.now(timezone.utc)
        return {
            "extraction_mode": extraction_mode,
            "node_transitions": [
                NodeTransition(
                    node="classify_extraction_mode",
                    event="completed",
                    created_at=now,
                ).model_dump(mode="json"),
            ],
        }

    return _classify_node


def _filter_harmonisation_items(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop items that fail evidence validation before they reach state."""
    valid = []
    for item in raw_items:
        try:
            HarmonisationItem.model_validate(item)
            valid.append(item)
        except Exception:
            pass
    return valid


def make_draft_proposal_node(
    llm: LLMCallable,
    role_config: RoleConfig,
    registry: SkillRegistry,
) -> Callable[[OnboardingGraphState], Awaitable[dict[str, Any]]]:
    """Return a draft_proposal node function that uses the given LLM callable.

    Raises ValueError when reference_metadata is absent from state — the node
    cannot produce well-anchored prose without cohort context.
    """

    _ = registry  # skill loading is wired in future slices

    async def _draft_proposal_node(state: OnboardingGraphState) -> dict[str, Any]:
        reference_metadata = state.get("reference_metadata")
        if reference_metadata is None:
            raise ValueError(
                "draft_proposal requires reference_metadata in state; "
                "gather_reference_metadata must run first"
            )

        source_summary = state.get("source_summary") or ""
        catalog_hits = state.get("existing_catalog_hits") or []
        messages = [
            {
                "role": "user",
                "content": (
                    f"source_summary: {source_summary}\n"
                    f"existing_catalog_hits: {catalog_hits}\n"
                    f"reference_metadata: {reference_metadata}"
                ),
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

        raw_harmonisation = result.get("harmonisation_items") or []
        filtered_harmonisation = _filter_harmonisation_items(raw_harmonisation)

        return {
            "proposal": result["proposal"],
            "enum_gap_proposals": result.get("enum_gap_proposals", []),
            "harmonisation_items": filtered_harmonisation,
            "suggest_human_apply": result.get("suggest_human_apply", []),
            "llm_calls": [llm_record.model_dump(mode="json")],
            "loaded_skills": [],
            "node_transitions": [
                NodeTransition(node="draft_proposal", event="completed", created_at=now).model_dump(mode="json"),
            ],
        }

    return _draft_proposal_node


def EDGE_NEXT_FROM_DRAFT(state: OnboardingGraphState) -> str:
    """Conditional edge out of draft_proposal; reads extraction_mode deterministically."""
    if state.get("extraction_mode") == "custom_python":
        return "draft_script"
    return END


def build_research_draft_graph(
    *,
    checkpointer: Any,
    research_llm: LLMCallable,
    draft_llm: LLMCallable,
    role_configs: dict[AgentRole, RoleConfig],
    registry: SkillRegistry,
) -> Any:
    """Compile the research → draft_proposal graph (slice 8 / legacy shape)."""

    research_node = make_research_node(research_llm, role_configs[AgentRole.RESEARCHER], registry)
    draft_node = make_draft_proposal_node(draft_llm, role_configs[AgentRole.PROPOSAL_DRAFTER], registry)

    graph = StateGraph(OnboardingGraphState)
    graph.add_node("research", research_node)
    graph.add_node("draft_proposal", draft_node)
    graph.add_edge(START, "research")
    graph.add_edge("research", "draft_proposal")
    graph.add_edge("draft_proposal", END)
    return graph.compile(checkpointer=checkpointer)


def build_reference_metadata_graph(
    *,
    checkpointer: Any,
    research_llm: LLMCallable,
    cohort_lookup: CohortLookupCallable,
    extraction_mode_classifier: ExtractionModeCallable,
    draft_llm: LLMCallable,
    role_configs: dict[AgentRole, RoleConfig],
    registry: SkillRegistry,
) -> Any:
    """Compile the full graph: research → (gather + classify in parallel) → draft_proposal."""

    research_node = make_research_node(research_llm, role_configs[AgentRole.RESEARCHER], registry)
    gather_node = make_gather_reference_metadata_node(cohort_lookup)
    classify_node = make_classify_extraction_mode_node(extraction_mode_classifier)
    draft_node = make_draft_proposal_node(draft_llm, role_configs[AgentRole.PROPOSAL_DRAFTER], registry)

    async def _draft_script_placeholder(state: OnboardingGraphState) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "node_transitions": [
                NodeTransition(node="draft_script", event="placeholder", created_at=now).model_dump(mode="json"),
            ],
        }

    graph = StateGraph(OnboardingGraphState)
    graph.add_node("research", research_node)
    graph.add_node("gather_reference_metadata", gather_node)
    graph.add_node("classify_extraction_mode", classify_node)
    graph.add_node("draft_proposal", draft_node)
    graph.add_node("draft_script", _draft_script_placeholder)

    graph.add_edge(START, "research")
    graph.add_edge("research", "gather_reference_metadata")
    graph.add_edge("research", "classify_extraction_mode")
    graph.add_edge("gather_reference_metadata", "draft_proposal")
    graph.add_edge("classify_extraction_mode", "draft_proposal")
    graph.add_conditional_edges("draft_proposal", EDGE_NEXT_FROM_DRAFT, ["draft_script", END])
    graph.add_edge("draft_script", END)
    return graph.compile(checkpointer=checkpointer)


__all__ = [
    "CohortLookupCallable",
    "EDGE_NEXT_FROM_DRAFT",
    "ExtractionModeCallable",
    "LLMCallable",
    "OnboardingGraphState",
    "build_hello_world_graph",
    "build_reference_metadata_graph",
    "build_research_draft_graph",
    "initial_graph_update",
    "llm_call_graph_update",
    "make_classify_extraction_mode_node",
    "make_draft_proposal_node",
    "make_gather_reference_metadata_node",
    "make_research_node",
    "user_input_graph_update",
]
