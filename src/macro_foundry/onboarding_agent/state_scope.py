
"""State Definitions and Pydantic Schemas for Research Scoping.

This defines the state objects and structured schemas used for
the research agent scoping workflow, including researcher state management and output schemas.
"""

from typing_extensions import Optional, List

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field

# ===== STATE DEFINITIONS =====

class AgentInputState(MessagesState):
    """Input state for the full agent - only contains messages from user input."""
    pass

class AgentState(MessagesState):
    """
    Main state for the full multi-agent research system.

    Extends MessagesState with additional fields for research coordination.
    Note: Some fields are duplicated across different state classes for proper
    state management between subgraphs and the main workflow.
    """

    # Series brief generated from user conversation history
    series_brief: Optional[str]
    need_clarification: Optional[bool]
    clarification_question: Optional[str]
    clarification_reasons: List[str]


# ===== STRUCTURED OUTPUT SCHEMAS =====

class ClarifyWithUser(BaseModel):
    """Schema for user clarification decision and questions."""

    need_clarification: bool = Field(
        description="Whether the user needs to be asked a clarifying question.",
    )
    question: str = Field(
        description="A question to ask the user to clarify the onboarding series scope",
    )
    verification: str = Field(
        description="Verify message that we will start series onboarding after the user has provided the necessary information.",
    )

class SeriesBrief(BaseModel):
    """Schema for structured series brief generation."""

    series_brief: str = Field(
        description="A brief description of the economic or financial data series to be onboarded.",
    )
    needs_clarification: bool = Field(
        description="Whether clarification is needed before a safe brief can be written.",
    )
    clarification_question: str = Field(
        description="One concise question to ask the user if clarification is needed. Empty otherwise.",
    )
    clarification_reasons: List[str] = Field(
        default_factory=list,
        description="Short reasons why clarification is needed.",
    )
