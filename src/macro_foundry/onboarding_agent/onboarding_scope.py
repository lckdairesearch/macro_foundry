
"""Series onboarding scoping workflow.

Three-node scoping graph:
  - clarify_with_user: completeness check. Asks the user for missing info.
  - verify_identifier: identifier-vs-description conflict check via web_search.
  - write_series_brief: pure author of the onboarding handoff brief.

The back-edge from verify_identifier to clarify_with_user is bounded by
MAX_VERIFICATION_ATTEMPTS to prevent infinite loops on ambiguous cases.

All `with_structured_output` calls pass `strict=True`. This makes langchain
convert the schema to OpenAI's strict format on the wire, which guarantees
`additionalProperties: false` on every object regardless of whether the
Pydantic class was imported with `ConfigDict(extra="forbid")` (defense
against stale module caches when running under `langgraph dev`).

The model is built with `streaming=False`. langchain-openai's streaming code
path for the Responses API does not apply the strict schema conversion that
`with_structured_output(..., strict=True)` requires, so OpenAI rejects the
schema as missing `additionalProperties: false`. The non-streaming path
builds the payload correctly. langgraph still streams at the graph-event
level; this only forces each LLM call to be a single synchronous request.

verification_conflict is a single-use slot. clarify_with_user consumes it on
entry (captures it into a local variable for the prompt) and unconditionally
clears it on exit. Without this discipline, the slot would persist across
user turns and the clarification prompt's "if non-empty, ask only about this"
rule would keep re-asking the same conflict question on every turn,
regardless of the user's answer. The conflict context survives in the
message history; verify_identifier re-detects any unresolved mismatch from
the updated transcript.
"""

from typing_extensions import Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, get_buffer_string
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

try:
    from macro_foundry.onboarding_agent.prompts import (
        clarify_with_user_instructions,
        transform_messages_into_series_brief_prompt,
        verify_identifier_instructions,
    )
    from macro_foundry.onboarding_agent.state_scope import (
        AgentInputState,
        AgentState,
        ClarifyWithUser,
        SeriesBrief,
        VerificationFindings,
        VerifyIdentifier,
    )
except ModuleNotFoundError:
    from prompts import (
        clarify_with_user_instructions,
        transform_messages_into_series_brief_prompt,
        verify_identifier_instructions,
    )
    from state_scope import (
        AgentInputState,
        AgentState,
        ClarifyWithUser,
        SeriesBrief,
        VerificationFindings,
        VerifyIdentifier,
    )


MAX_VERIFICATION_ATTEMPTS = 2


def get_model():
    """Build the model lazily so importing the module does not require credentials.

    `streaming=False` is required: see module docstring.
    """
    return init_chat_model(
        model="openai:gpt-5.1",
        temperature=1,
        use_responses_api=True,
        streaming=False,
    )


def _format_findings(findings: VerificationFindings | None) -> str:
    """Render verification findings for prompt interpolation."""
    if findings is None:
        return "(no prior verification findings)"
    parts = []
    if findings.canonical_name:
        parts.append(f"canonical_name: {findings.canonical_name}")
    if findings.source_url:
        parts.append(f"source_url: {findings.source_url}")
    if findings.notes:
        parts.append(f"notes: {findings.notes}")
    return "\n".join(parts) if parts else "(no prior verification findings)"


def clarify_with_user(state: AgentState) -> Command[Literal["verify_identifier", "__end__"]]:
    """Completeness gate. Asks the user for missing info or resolves a surfaced conflict.

    If verification_conflict is set, the question targets that conflict only;
    otherwise the general identification criteria apply.

    verification_conflict is a single-use slot: this node consumes it on entry
    (captured into a local variable for the prompt) and unconditionally clears
    it on exit via `cleared_slots`. Every exit Command merges in `cleared_slots`,
    so neither branch can leak the flag to the next turn. The conflict context
    survives in the message history; verify_identifier will re-detect any
    unresolved mismatch from the updated transcript.
    """
    conflict_input = state.get("verification_conflict") or ""

    structured_output_model = get_model().with_structured_output(
        ClarifyWithUser,
        tools=[{"type": "web_search"}],
        strict=True,
    )

    response = structured_output_model.invoke([
        HumanMessage(
            content=clarify_with_user_instructions.format(
                messages=get_buffer_string(messages=state["messages"]),
                verification_conflict=conflict_input,
            )
        )
    ])

    cleared_slots = {
        "verification_conflict": "",
        "clarification_reasons": [],
    }

    if response.need_clarification:
        return Command(
            goto=END,
            update={
                **cleared_slots,
                "need_clarification": True,
                "clarification_question": response.question,
                "messages": [AIMessage(content=response.question)],
            },
        )

    return Command(
        goto="verify_identifier",
        update={
            **cleared_slots,
            "need_clarification": False,
            "clarification_question": "",
            "messages": [AIMessage(content=response.verification)],
        },
    )


def verify_identifier(state: AgentState) -> Command[Literal["clarify_with_user", "write_series_brief"]]:
    """Web-verify that the identifier matches the user's description.

    On conflict, route back to clarify_with_user with a specific conflict context,
    up to MAX_VERIFICATION_ATTEMPTS. After the cap, proceed to write_series_brief
    with the unresolved conflict surfaced rather than looping further.
    """
    structured_output_model = get_model().with_structured_output(
        VerifyIdentifier,
        tools=[{"type": "web_search"}],
        strict=True,
    )

    response = structured_output_model.invoke([
        HumanMessage(
            content=verify_identifier_instructions.format(
                messages=get_buffer_string(messages=state["messages"]),
            )
        )
    ])

    attempts = state.get("verification_attempts", 0) + 1

    if response.has_conflict and attempts <= MAX_VERIFICATION_ATTEMPTS:
        bounce_message = (
            "Identifier verification surfaced a conflict that needs the user to resolve:\n"
            f"{response.conflict_description}"
        )
        return Command(
            goto="clarify_with_user",
            update={
                "verification_findings": response.findings,
                "verification_conflict": response.conflict_description,
                "verification_attempts": attempts,
                "messages": [AIMessage(content=bounce_message)],
            },
        )

    if response.has_conflict:
        forced_message = (
            f"Identifier verification still reports a conflict after {MAX_VERIFICATION_ATTEMPTS} attempts: "
            f"{response.conflict_description}. Proceeding to brief; the downstream agent should treat the conflict as unresolved."
        )
        return Command(
            goto="write_series_brief",
            update={
                "verification_findings": response.findings,
                "verification_conflict": response.conflict_description,
                "verification_attempts": attempts,
                "messages": [AIMessage(content=forced_message)],
            },
        )

    return Command(
        goto="write_series_brief",
        update={
            "verification_findings": response.findings,
            "verification_conflict": "",
            "verification_attempts": attempts,
        },
    )


def write_series_brief(state: AgentState) -> Command[Literal["__end__"]]:
    """Pure author of the onboarding handoff brief.

    Reads verification_findings as authoritative and fills gaps via targeted
    web_search. Does not gate or vote on clarification.
    """
    structured_output_model = get_model().with_structured_output(
        SeriesBrief,
        tools=[{"type": "web_search"}],
        strict=True,
    )

    response = structured_output_model.invoke([
        HumanMessage(
            content=transform_messages_into_series_brief_prompt.format(
                messages=get_buffer_string(state.get("messages", [])),
                verification_findings=_format_findings(state.get("verification_findings")),
            )
        )
    ])

    brief_message = (
        "The following series brief has been generated based on the conversation history:\n\n\n"
        f"{response.series_brief}"
    )

    return Command(
        goto=END,
        update={
            "series_brief": response.series_brief,
            "messages": [AIMessage(content=brief_message)],
        },
    )


series_scope_builder = StateGraph(AgentState, input_schema=AgentInputState)
series_scope_builder.add_node("clarify_with_user", clarify_with_user)
series_scope_builder.add_node(
    "verify_identifier",
    verify_identifier,
    destinations=("clarify_with_user", "write_series_brief"),
)
series_scope_builder.add_node("write_series_brief", write_series_brief)
series_scope_builder.add_edge(START, "clarify_with_user")

scope_series_onboarding = series_scope_builder.compile()
