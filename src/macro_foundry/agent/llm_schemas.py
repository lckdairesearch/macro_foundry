"""Pydantic structured-output schemas for OpenAI LLM callables."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResearchOutput(BaseModel):
    """Structured output for the researcher role."""

    source_summary: str = Field(default="")
    existing_catalog_hits: list[dict[str, Any]] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    credential_gap_proposals: list[dict[str, Any]] = Field(default_factory=list)


class DraftOutput(BaseModel):
    """Structured output for the proposal_drafter role."""

    proposal: dict[str, Any] | None = None
    enum_gap_proposals: list[dict[str, Any]] = Field(default_factory=list)
    harmonisation_items: list[dict[str, Any]] = Field(default_factory=list)
    suggest_human_apply: list[dict[str, Any]] = Field(default_factory=list)


class ReviewerOutput(BaseModel):
    """Structured output for governance and data-correctness reviewer roles."""

    findings: list[dict[str, Any]] = Field(default_factory=list)
    bounce_to_drafter: bool = False


class ApprovalOutput(BaseModel):
    """Structured output for the approval_parser role."""

    edit_instructions: str = Field(default="")


class TestReviewOutput(BaseModel):
    """Structured output for the test_reviewer role."""

    summary: str = Field(default="")
    passed: bool = True


__all__ = ["ApprovalOutput", "DraftOutput", "ResearchOutput", "ReviewerOutput", "TestReviewOutput"]
