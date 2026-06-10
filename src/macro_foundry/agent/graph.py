"""LangGraph definitions for onboarding session persistence."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from operator import add
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from macro_foundry.agent.catalog import WriteToolsProtocol, make_apply_catalog_node
from macro_foundry.agent.channel import Channel
from macro_foundry.agent.credential_gap import make_credential_gap_wait_node
from macro_foundry.agent.enum_gap import make_enum_gap_wait_node
from macro_foundry.agent.executor import (
    FirstRunLogReaderProtocol,
    FirstRunWriteToolsProtocol,
    OnboardingPackageStoreProtocol,
    TestReviewerProtocol,
    make_emit_package_node,
    make_monitor_first_run_node,
    make_test_review_node,
    make_trigger_first_run_node,
)
from macro_foundry.agent.gate import (
    ApprovalLLMCallable,
    GateOutcome,
    PickerCallable,
    is_structural_edit,
    make_apply_small_edit_node,
    make_gate_1_wait_node,
)
from macro_foundry.agent.onboarding_state import (
    EnumGapProposal,
    LLMCallRecord,
    NodeTransition,
    RawMessage,
    TranscriptEntry,
)
from macro_foundry.agent.proposal import CredentialGapProposal, HarmonisationItem, ReferenceMetadata
from macro_foundry.agent.review import ReviewBundle
from macro_foundry.agent.roles import AgentRole, RoleConfig
from macro_foundry.agent.skills import SkillRegistry

# Type alias for a single-call LLM callable used by research and draft nodes.
# Receives the assembled messages list; returns a dict with content + usage metadata.
LLMCallable = Callable[[list[dict[str, str]]], Awaitable[dict[str, Any]]]

# Reviewer callable accepts an optional task_hint for within-role model tiering.
ReviewerLLMCallable = Callable[..., Awaitable[dict[str, Any]]]

# Write tools that must never appear in a reviewer's bound_tools set.
_WRITE_TOOL_NAMES: frozenset[str] = frozenset({
    "macrodb_write",
    "macrodb_write_proposals",
    "selector_sandbox",
})

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
    checkpoint_position: str | None
    abort_reason: str | None
    # Research outputs
    source_summary: str | None
    existing_catalog_hits: list[dict[str, Any]]
    ambiguity_flags: list[str]
    credential_gap_proposals: list[dict[str, Any]]
    credential_gap_resolutions: list[dict[str, Any]]
    # Reference metadata (gather_reference_metadata node)
    reference_metadata: dict[str, Any] | None
    is_first_in_family: bool | None
    # Extraction mode (classify_extraction_mode node and reviewer fan-out)
    extraction_mode: str | None
    # Proposal outputs
    proposal: dict[str, Any] | None
    enum_gap_proposals: list[dict[str, Any]]
    enum_gap_resolutions: list[dict[str, Any]]
    coerce_hints: dict[str, str]
    coerce_rationales: dict[str, str]
    harmonisation_items: list[dict[str, Any]]
    suggest_human_apply: list[dict[str, Any]]
    # Reviewer fan-out outputs (issue 44)
    review_cycle: int
    governance_review: dict[str, Any] | None
    data_correctness_review: dict[str, Any] | None
    # Gate 1 state (issue 45)
    gate_1_outcome: str | None
    gate_1_approved: bool
    gate_1_applied: bool
    small_edit_instructions: str | None
    collision_choice: str | None
    collision_detail: dict[str, Any] | None
    gate_2_escalation: bool
    unapprove_rejected: bool
    # Post-Gate-1 executor state (issue 50)
    applied_catalog: dict[str, Any]
    first_run_payload: Any
    first_run_run_date: Any
    first_run: dict[str, Any]
    test_review: dict[str, Any]
    onboarding_package: dict[str, Any]


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
            "credential_gap_proposals": _filter_credential_gap_proposals(
                result.get("credential_gap_proposals", [])
            ),
            "llm_calls": [llm_record.model_dump(mode="json")],
            "loaded_skills": [],
            "node_transitions": [
                NodeTransition(node="research", event="completed", created_at=now).model_dump(mode="json"),
            ],
        }

    return _research_node


def _filter_credential_gap_proposals(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop credential-gap proposals missing ADR 0016 evidence fields."""
    valid = []
    for item in raw_items:
        try:
            proposal = CredentialGapProposal.model_validate(item)
            valid.append(proposal.model_dump(mode="json"))
        except ValidationError:
            pass
    return valid


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
        except ValidationError:
            pass
    return valid


def _filter_enum_gap_proposals(
    raw_items: list[dict[str, Any]],
    *,
    suppressed_enum_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Drop enum gaps that fail ADR 0014 allowlist or evidence validation."""
    valid = []
    suppressed = suppressed_enum_paths or set()
    for item in raw_items:
        try:
            proposal = EnumGapProposal.model_validate(item)
            if proposal.enum_path in suppressed:
                continue
            valid.append(proposal.model_dump(mode="json"))
        except ValidationError:
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
        coerce_hints = state.get("coerce_hints") or {}
        coerce_rationales = state.get("coerce_rationales") or {}
        messages = [
            {
                "role": "user",
                "content": (
                    f"source_summary: {source_summary}\n"
                    f"existing_catalog_hits: {catalog_hits}\n"
                    f"reference_metadata: {reference_metadata}\n"
                    f"coerce_hints: {coerce_hints}\n"
                    f"coerce_rationales: {coerce_rationales}"
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
        enum_gap_proposals = _filter_enum_gap_proposals(
            result.get("enum_gap_proposals") or [],
            suppressed_enum_paths=set(coerce_hints),
        )

        return {
            "proposal": None if enum_gap_proposals else result["proposal"],
            "enum_gap_proposals": enum_gap_proposals,
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
    if state.get("enum_gap_proposals"):
        return "enum_gap_wait"
    if state.get("extraction_mode") == "custom_python":
        return "draft_script"
    return END


def EDGE_NEXT_FROM_ENUM_GAP_WAIT(state: OnboardingGraphState) -> str:
    """Conditional edge out of enum_gap_wait."""
    if state.get("checkpoint_position") == "enum_gap_wait" or state.get("abort_reason"):
        return END
    return "draft_proposal"


def EDGE_NEXT_FROM_RESEARCH(state: OnboardingGraphState) -> str:
    """Conditional edge out of research."""
    if state.get("credential_gap_proposals") and not state.get("credential_gap_resolutions"):
        return "credential_gap_wait"
    return "gather_reference_metadata"


def EDGE_NEXT_FROM_CREDENTIAL_GAP_WAIT(state: OnboardingGraphState) -> str:
    """Conditional edge out of credential_gap_wait."""
    if state.get("abort_reason") or state.get("checkpoint_position") == "credential_gap_wait":
        return END
    if state.get("credential_gap_resolutions"):
        return "research"
    return END


def EDGE_NEXT_FROM_DRAFT_FOR_REVIEW(state: OnboardingGraphState) -> str:
    """Conditional edge out of draft_proposal in the full onboarding graph."""
    if state.get("enum_gap_proposals"):
        return "enum_gap_wait"
    if state.get("extraction_mode") == "custom_python":
        return "draft_script"
    return "governance_review"


def EDGE_NEXT_FROM_GATE_1_WAIT(state: OnboardingGraphState) -> str:
    """Conditional edge out of Gate 1."""
    outcome = state.get("gate_1_outcome")
    if outcome == GateOutcome.APPROVE.value:
        return "unapproval_window"
    if outcome == GateOutcome.REQUEST_CHANGES.value:
        return "draft_proposal" if is_structural_edit(state.get("small_edit_instructions") or "") else "apply_small_edit"
    return END


def EDGE_NEXT_FROM_APPLY_SMALL_EDIT(state: OnboardingGraphState) -> str:
    """Conditional edge after applying parsed small-edit instructions."""
    if state.get("gate_2_escalation") or state.get("collision_choice"):
        return END
    return "gate_1_wait"


async def _unapproval_window_node(state: OnboardingGraphState) -> dict[str, Any]:
    """Record the armed-but-not-applied window before catalog writes."""
    now = datetime.now(timezone.utc)
    return {
        "gate_1_applied": False,
        "node_transitions": [
            NodeTransition(
                node="unapproval_window",
                event="armed",
                created_at=now,
            ).model_dump(mode="json")
        ],
    }


def make_governance_review_node(
    llm: ReviewerLLMCallable,
    role_config: RoleConfig,
    registry: SkillRegistry,
) -> Callable[[OnboardingGraphState], Awaitable[dict[str, Any]]]:
    """Return a governance_review node bound to read-only tools only."""

    bound_tools: frozenset[str] = frozenset(role_config.tools) - _WRITE_TOOL_NAMES
    _ = registry  # skill loading wired in a later slice

    async def _governance_review_node(state: OnboardingGraphState) -> dict[str, Any]:
        proposal = state.get("proposal") or {}
        enum_gap_proposals = state.get("enum_gap_proposals") or []
        extraction_mode = state.get("extraction_mode") or "config_only"
        cycle = (state.get("review_cycle") or 0) + 1

        task_hint: str | None = None
        if extraction_mode == "custom_python":
            task_hint = "selector_code_review"

        messages = [
            {
                "role": "user",
                "content": f"proposal: {proposal}\nenum_gap_proposals: {enum_gap_proposals}",
            }
        ]
        result = await llm(messages, task_hint=task_hint)

        now = datetime.now(timezone.utc)
        llm_record = LLMCallRecord(
            role=role_config.role.value,
            task_hint=task_hint,
            provider=role_config.provider.value,
            model=role_config.default_model,
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            total_tokens=result["total_tokens"],
            cost_estimate_usd=result["cost_estimate_usd"],
            latency_ms=result["latency_ms"],
            created_at=now,
        )

        bundle = ReviewBundle(
            specialty="governance",
            findings=result.get("findings", []),
            review_cycle=cycle,
            bounce_to_drafter=result.get("bounce_to_drafter", False),
        )

        return {
            "governance_review": bundle.model_dump(mode="json"),
            "review_cycle": cycle,
            "llm_calls": [llm_record.model_dump(mode="json")],
            "loaded_skills": [],
            "node_transitions": [
                NodeTransition(node="governance_review", event="completed", created_at=now).model_dump(mode="json"),
            ],
        }

    _governance_review_node.bound_tools = bound_tools  # type: ignore[attr-defined]
    return _governance_review_node


def make_data_correctness_review_node(
    llm: ReviewerLLMCallable,
    role_config: RoleConfig,
    registry: SkillRegistry,
) -> Callable[[OnboardingGraphState], Awaitable[dict[str, Any]]]:
    """Return a data_correctness_review node bound to read-only tools only."""

    bound_tools: frozenset[str] = frozenset(role_config.tools) - _WRITE_TOOL_NAMES
    _ = registry

    async def _data_correctness_review_node(state: OnboardingGraphState) -> dict[str, Any]:
        proposal = state.get("proposal") or {}
        cycle = (state.get("review_cycle") or 0) + 1

        messages = [{"role": "user", "content": f"proposal: {proposal}"}]
        result = await llm(messages, task_hint=None)

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

        bundle = ReviewBundle(
            specialty="data_correctness",
            findings=result.get("findings", []),
            review_cycle=cycle,
            bounce_to_drafter=result.get("bounce_to_drafter", False),
        )

        return {
            "data_correctness_review": bundle.model_dump(mode="json"),
            "llm_calls": [llm_record.model_dump(mode="json")],
            "loaded_skills": [],
            "node_transitions": [
                NodeTransition(node="data_correctness_review", event="completed", created_at=now).model_dump(mode="json"),
            ],
        }

    _data_correctness_review_node.bound_tools = bound_tools  # type: ignore[attr-defined]
    return _data_correctness_review_node


def build_onboarding_graph(
    *,
    checkpointer: Any,
    research_llm: LLMCallable,
    cohort_lookup: CohortLookupCallable,
    extraction_mode_classifier: ExtractionModeCallable,
    draft_llm: LLMCallable,
    governance_llm: ReviewerLLMCallable,
    data_correctness_llm: ReviewerLLMCallable,
    approval_llm: ApprovalLLMCallable,
    gate_1_picker: PickerCallable,
    channel: Channel,
    write_tools: WriteToolsProtocol | FirstRunWriteToolsProtocol,
    run_logs: FirstRunLogReaderProtocol,
    test_reviewer: TestReviewerProtocol,
    package_store: OnboardingPackageStoreProtocol,
    role_configs: dict[AgentRole, RoleConfig],
    registry: SkillRegistry,
    enum_gap_wait_node: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
    credential_gap_wait_node: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
    unique_checker: Callable[..., Awaitable[dict[str, Any] | None]] | None = None,
    collision_picker: PickerCallable | None = None,
) -> Any:
    """Compile the canonical end-to-end onboarding graph.

    The graph intentionally keeps external services injectable so integration
    tests can drive the real runtime and database writes without live LLM or
    provider access.
    """

    research_node = make_research_node(research_llm, role_configs[AgentRole.RESEARCHER], registry)
    gather_node = make_gather_reference_metadata_node(cohort_lookup)
    classify_node = make_classify_extraction_mode_node(extraction_mode_classifier)
    draft_node = make_draft_proposal_node(draft_llm, role_configs[AgentRole.PROPOSAL_DRAFTER], registry)
    gov_node = make_governance_review_node(
        governance_llm, role_configs[AgentRole.GOVERNANCE_REVIEWER], registry
    )
    data_node = make_data_correctness_review_node(
        data_correctness_llm, role_configs[AgentRole.DATA_CORRECTNESS_REVIEWER], registry
    )
    gate_node = make_gate_1_wait_node(
        channel=channel,
        approval_llm=approval_llm,
        picker=gate_1_picker,
    )
    apply_small_edit_node = make_apply_small_edit_node(
        unique_checker=unique_checker or _no_unique_collision,
        collision_picker=collision_picker,
    )
    apply_node = make_apply_catalog_node(write_tools=write_tools)  # type: ignore[arg-type]
    trigger_node = make_trigger_first_run_node(write_tools=write_tools)  # type: ignore[arg-type]
    monitor_node = make_monitor_first_run_node(run_logs=run_logs)
    test_review_node = make_test_review_node(reviewer=test_reviewer)
    emit_node = make_emit_package_node(package_store=package_store)
    enum_wait = enum_gap_wait_node or make_enum_gap_wait_node()
    credential_wait = credential_gap_wait_node or make_credential_gap_wait_node(
        write_tools=write_tools,
        environ={},
        probe=lambda _name, _value: "ok",  # type: ignore[return-value]
    )

    async def _draft_script_placeholder(state: OnboardingGraphState) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "node_transitions": [
                NodeTransition(
                    node="draft_script",
                    event="skipped_config_only" if state.get("extraction_mode") == "config_only" else "completed",
                    created_at=now,
                ).model_dump(mode="json")
            ],
        }

    graph = StateGraph(OnboardingGraphState)
    graph.add_node("research", research_node)
    graph.add_node("credential_gap_wait", credential_wait)
    graph.add_node("gather_reference_metadata", gather_node)
    graph.add_node("classify_extraction_mode", classify_node)
    graph.add_node("draft_proposal", draft_node)
    graph.add_node("enum_gap_wait", enum_wait)
    graph.add_node("draft_script", _draft_script_placeholder)
    graph.add_node("governance_review", gov_node)
    graph.add_node("data_correctness_review", data_node)
    graph.add_node("gate_1_wait", gate_node)
    graph.add_node("apply_small_edit", apply_small_edit_node)
    graph.add_node("unapproval_window", _unapproval_window_node)
    graph.add_node("apply_catalog", apply_node)
    graph.add_node("trigger_first_run", trigger_node)
    graph.add_node("monitor_first_run", monitor_node)
    graph.add_node("test_review", test_review_node)
    graph.add_node("emit_package", emit_node)

    graph.add_edge(START, "research")
    graph.add_conditional_edges(
        "research",
        EDGE_NEXT_FROM_RESEARCH,
        ["credential_gap_wait", "gather_reference_metadata"],
    )
    graph.add_conditional_edges(
        "credential_gap_wait",
        EDGE_NEXT_FROM_CREDENTIAL_GAP_WAIT,
        ["research", END],
    )
    graph.add_edge("gather_reference_metadata", "classify_extraction_mode")
    graph.add_edge("classify_extraction_mode", "draft_proposal")
    graph.add_conditional_edges(
        "draft_proposal",
        EDGE_NEXT_FROM_DRAFT_FOR_REVIEW,
        ["enum_gap_wait", "draft_script", "governance_review"],
    )
    graph.add_conditional_edges("enum_gap_wait", EDGE_NEXT_FROM_ENUM_GAP_WAIT, ["draft_proposal", END])
    graph.add_edge("draft_script", "governance_review")
    graph.add_edge("governance_review", "data_correctness_review")
    graph.add_edge("data_correctness_review", "gate_1_wait")
    graph.add_conditional_edges(
        "gate_1_wait",
        EDGE_NEXT_FROM_GATE_1_WAIT,
        ["unapproval_window", "apply_small_edit", "draft_proposal", END],
    )
    graph.add_conditional_edges(
        "apply_small_edit",
        EDGE_NEXT_FROM_APPLY_SMALL_EDIT,
        ["gate_1_wait", END],
    )
    graph.add_edge("unapproval_window", "apply_catalog")
    graph.add_edge("apply_catalog", "trigger_first_run")
    graph.add_edge("trigger_first_run", "monitor_first_run")
    graph.add_edge("monitor_first_run", "test_review")
    graph.add_edge("test_review", "emit_package")
    graph.add_edge("emit_package", END)
    return graph.compile(checkpointer=checkpointer)


async def _no_unique_collision(*_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
    return None


__all__ = [
    "CohortLookupCallable",
    "EDGE_NEXT_FROM_ENUM_GAP_WAIT",
    "EDGE_NEXT_FROM_APPLY_SMALL_EDIT",
    "EDGE_NEXT_FROM_DRAFT",
    "EDGE_NEXT_FROM_DRAFT_FOR_REVIEW",
    "EDGE_NEXT_FROM_GATE_1_WAIT",
    "EDGE_NEXT_FROM_RESEARCH",
    "EDGE_NEXT_FROM_CREDENTIAL_GAP_WAIT",
    "ExtractionModeCallable",
    "LLMCallable",
    "OnboardingGraphState",
    "ReviewerLLMCallable",
    "build_onboarding_graph",
    "initial_graph_update",
    "llm_call_graph_update",
    "make_classify_extraction_mode_node",
    "make_data_correctness_review_node",
    "make_draft_proposal_node",
    "make_gather_reference_metadata_node",
    "make_governance_review_node",
    "make_research_node",
    "user_input_graph_update",
]
