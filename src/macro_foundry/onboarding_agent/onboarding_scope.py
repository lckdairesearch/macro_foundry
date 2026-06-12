
"""Series onboarding scoping workflow.

This module implements the scoping phase of the onboarding workflow, where we:
1. Decide whether the user's request needs clarification
2. Generate a structured series brief from the conversation

The workflow uses structured output so the clarification decision and
series brief generation remain deterministic and easy to inspect.
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
    )
    from macro_foundry.onboarding_agent.state_scope import (
        AgentInputState,
        AgentState,
        ClarifyWithUser,
        SeriesBrief,
    )
except ModuleNotFoundError:
    from prompts import (
        clarify_with_user_instructions,
        transform_messages_into_series_brief_prompt,
    )
    from state_scope import AgentInputState, AgentState, ClarifyWithUser, SeriesBrief


def get_model():
    """Build the model lazily so importing the module does not require credentials."""
    return init_chat_model(model="openai:gpt-5.4", temperature=1, use_responses_api=True)


def clarify_with_user(state: AgentState) -> Command[Literal["write_series_brief", "__end__"]]:
    """Check whether the user has specified enough to identify the target series."""
    structured_output_model = get_model().with_structured_output(
        ClarifyWithUser,
        tools=[{"type": "web_search"}],
    )


    response = structured_output_model.invoke([
        HumanMessage(
            content=clarify_with_user_instructions.format(
                messages=get_buffer_string(messages=state["messages"]),
            )
        )
    ])

    if response.need_clarification:
        return Command(
            goto=END,
            update={
                "need_clarification": True,
                "clarification_question": response.question,
                "clarification_reasons": state.get("clarification_reasons", []),
                "messages": [AIMessage(content=response.question)],
            },
        )

    return Command(
        goto="write_series_brief",
        update={
            "need_clarification": False,
            "clarification_question": "",
            "clarification_reasons": [],
            "messages": [AIMessage(content=response.verification)],
        },
    )


def write_series_brief(state: AgentState) -> Command[Literal["clarify_with_user", "__end__"]]:
    """Turn the conversation history into a concise onboarding-ready series brief."""

    structured_output_model = get_model().with_structured_output(
        SeriesBrief,
        tools=[{"type": "web_search"}],
    )


    response = structured_output_model.invoke([
        HumanMessage(
            content=transform_messages_into_series_brief_prompt.format(
                messages=get_buffer_string(state.get("messages", [])),
            )
        )
    ])

    if response.needs_clarification:
        reasons = "\n".join(f"- {reason}" for reason in response.clarification_reasons)
        blocker_context = (
            "The series brief quality check found that clarification is still needed.\n"
            f"{reasons}"
        )
        return Command(
            goto="clarify_with_user",
            update={
                "series_brief": "",
                "need_clarification": True,
                "clarification_question": response.clarification_question,
                "clarification_reasons": response.clarification_reasons,
                "messages": [AIMessage(content=blocker_context)],
            },
        )

    return Command(
        goto=END,
        update={
            "series_brief": response.series_brief,
            "need_clarification": False,
            "clarification_question": "",
            "clarification_reasons": [],
        },
    )


series_scope_builder = StateGraph(AgentState, input_schema=AgentInputState)
series_scope_builder.add_node("clarify_with_user", clarify_with_user)
series_scope_builder.add_node(
    "write_series_brief",
    write_series_brief,
    destinations=("clarify_with_user", END),
)
series_scope_builder.add_edge(START, "clarify_with_user")

scope_series_onboarding = series_scope_builder.compile()
