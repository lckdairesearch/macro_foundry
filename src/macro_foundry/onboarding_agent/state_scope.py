
"""State Definitions and Pydantic Schemas for Scoping.

State objects and structured-output schemas for the scoping workflow:
  - clarify_with_user   -> owns clarification_*
  - verify_identifier   -> owns verification_*
  - write_series_brief  -> owns series_brief

Fields are namespaced per node so responsibilities do not leak between them.

All schema classes set `extra="forbid"` so Pydantic emits
`additionalProperties: false` in the generated JSON schema. OpenAI's strict
structured-output mode (used by the Responses API with tools) requires this
on every object, including nested objects in `$defs`.
"""

from typing_extensions import Optional, List

from langgraph.graph import MessagesState
from pydantic import BaseModel, ConfigDict, Field


# ===== STATE DEFINITIONS =====

class AgentInputState(MessagesState):
    """Input state for the full agent - only contains messages from user input."""
    pass


class AgentState(MessagesState):
    """Main state for the scoping workflow.

    Fields are namespaced per node so each node owns one slice of state:
      - clarify_with_user  -> need_clarification, clarification_question, clarification_reasons
      - verify_identifier  -> verification_findings, verification_conflict, verification_attempts
      - write_series_brief -> series_brief
    """

    # clarify_with_user
    need_clarification: Optional[bool]
    clarification_question: Optional[str]
    clarification_reasons: List[str]

    # verify_identifier
    verification_findings: Optional["VerificationFindings"]
    verification_conflict: Optional[str]
    verification_attempts: int

    # write_series_brief
    series_brief: Optional[str]


# ===== STRUCTURED OUTPUT SCHEMAS =====

class ClarifyWithUser(BaseModel):
    """Schema for user clarification decision and questions."""

    model_config = ConfigDict(extra="forbid")

    need_clarification: bool = Field(
        description="Whether the user needs to be asked a clarifying question.",
    )
    question: str = Field(
        description="If need_clarification is True, a question to ask the user to clarify the onboarding series scope. Empty otherwise.",
    )
    verification: str = Field(
        description="If need_clarification is False, a message confirming that we will start series onboarding after the user has provided the necessary information. Empty otherwise.",
    )


class VerificationFindings(BaseModel):
    """Byproduct of identifier verification, reusable by write_series_brief.

    Only what verify_identifier surfaces while testing the conflict hypothesis.
    Brief writer fills the remaining gaps; verify_identifier must not drift into
    full attribute collection.
    """

    canonical_name: str = Field(
        default="",
        description="Canonical name confirmed via verification (e.g., 'Core CPI, seasonally adjusted'). Empty if not determined.",
    )
    source_url: str = Field(
        default="",
        description="Authoritative source URL surfaced during verification (e.g., the FRED series page). Empty if not found.",
    )
    notes: str = Field(
        default="",
        description="Short free-text notes captured as a byproduct (e.g., 'monthly, index 1982-1984=100'). Not exhaustive.",
    )


class VerifyIdentifier(BaseModel):
    """Schema for identifier-vs-description verification."""

    model_config = ConfigDict(extra="forbid")

    has_conflict: bool = Field(
        description="True if the identifier (e.g., FRED ticker) does not match the user's description.",
    )
    conflict_description: str = Field(
        default="",
        description="Short description of the mismatch, suitable for asking the user to resolve (e.g., 'CPILFESL is core CPI, but you asked for headline inflation'). Empty if no conflict.",
    )
    findings: VerificationFindings = Field(
        default_factory=VerificationFindings,
        description="Verified attributes surfaced during the conflict check. Passed forward so write_series_brief does not redo the same web searches.",
    )


class SeriesBrief(BaseModel):
    """Schema for series brief generation.

    Brief writer is a pure author: it produces the artifact and does not vote
    on whether more clarification is needed. That decision lives in
    clarify_with_user, gated by verify_identifier.
    """

    model_config = ConfigDict(extra="forbid")

    series_brief: str = Field(
        description="A brief description of the economic or financial data series to be onboarded.",
    )
