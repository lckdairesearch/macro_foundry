"""Pydantic structured-output schemas for OpenAI LLM callables."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


_STRICT_CONFIG = ConfigDict(extra="forbid")


class CatalogHitOutput(BaseModel):
    """Closed researcher output item for possible existing catalog matches."""

    model_config = _STRICT_CONFIG

    kind: Literal["series", "family", "series_family", "concept", "provider", "unknown"] = "unknown"
    id: str | None = None
    family_id: str | None = None
    series_family_id: str | None = None
    concept_id: str | None = None
    provider_id: str | None = None
    code: str | None = None
    name: str | None = None
    external_code: str | None = None
    provider_name: str | None = None
    rationale: str | None = None


class ProviderIdentityOutput(BaseModel):
    """Closed credential-gap provider identity output."""

    model_config = _STRICT_CONFIG

    kind: Literal["existing", "new"]
    existing_provider_id: str | None = None
    proposed_provider_name: str | None = None
    proposed_provider_homepage_url: str | None = None
    proposed_provider_doc_url: str | None = None


class CredentialGapProposalOutput(BaseModel):
    """Closed credential-gap proposal output."""

    model_config = _STRICT_CONFIG

    provider_identity: ProviderIdentityOutput
    proposed_env_var_name: str
    proposed_auth_scheme: str
    inferred_rate_limit_summary: str | None = None
    evidence_url: str
    evidence_snippet: str
    rationale: str


class DraftConceptOutput(BaseModel):
    model_config = _STRICT_CONFIG

    action: Literal["new", "existing"]
    code: str
    name: str
    description: str | None = None


class DraftFamilyOutput(BaseModel):
    model_config = _STRICT_CONFIG

    action: Literal["new", "existing"]
    code: str
    name: str
    concept_code: str
    geography_code: str
    description: str | None = None


class DraftSeriesOutput(BaseModel):
    model_config = _STRICT_CONFIG

    action: Literal["new", "existing"]
    code: str
    name: str
    description: str | None = None
    frequency: str
    measure: str
    unit_kind: str
    temporal_stock_flow: str
    unit_scale: str
    seasonal_adjustment: str
    annualized: bool = False
    origin_type: str = "ingested"
    is_active: bool = True
    measure_horizon: str | None = None
    price_basis: str | None = None
    currency_code: str | None = None
    reference_kind: str | None = None
    reference_year: int | None = None
    reference_label: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class DraftSeriesSourceOutput(BaseModel):
    model_config = _STRICT_CONFIG

    provider_name: str
    external_code: str
    external_name: str | None = None
    provider_role: str = "primary_source"
    priority: int = 1


class DraftIngestionFeedOutput(BaseModel):
    model_config = _STRICT_CONFIG

    selector_type: str
    selector_config_summary: str | None = None
    cron_schedule: str
    feed_method: str
    fetch_url: str | None = None
    is_active: bool = True


class DraftFamilyMemberOutput(BaseModel):
    model_config = _STRICT_CONFIG

    variant: str | None = None
    is_primary: bool = True


class DraftHierarchyEdgeOutput(BaseModel):
    model_config = _STRICT_CONFIG

    parent_series_code: str
    child_series_code: str
    edge_kind: str


class DraftProposalOutput(BaseModel):
    model_config = _STRICT_CONFIG

    concept: DraftConceptOutput
    family: DraftFamilyOutput
    series: DraftSeriesOutput
    source: DraftSeriesSourceOutput
    feed: DraftIngestionFeedOutput
    family_member: DraftFamilyMemberOutput
    hierarchy_edges: list[DraftHierarchyEdgeOutput] = Field(default_factory=list)


class EnumGapProposalOutput(BaseModel):
    """Closed enum-gap output item; graph-side validation applies ADR 0014 rules."""

    model_config = _STRICT_CONFIG

    enum_path: str
    proposed_value: str
    evidence_url: str
    evidence_snippet: str
    rationale: str


class HarmonisationItemOutput(BaseModel):
    """Closed harmonisation item; graph-side validation applies evidence rules."""

    model_config = _STRICT_CONFIG

    trigger: Literal["factual_incompleteness", "factual_error", "family_outlier", "house_voice_outlier"]
    target_series_code: str
    schema_field: str | None = None
    source_url: str | None = None
    cohort_members: list[str] | None = None
    shared_pattern: str | None = None
    divergence: str | None = None
    proposed_diff: str


class SuggestHumanApplyItemOutput(BaseModel):
    model_config = _STRICT_CONFIG

    schema_field: str
    target_series_code: str | None = None
    current_value: str | None = None
    proposed_value: str
    rationale: str


class ResearchOutput(BaseModel):
    """Structured output for the researcher role."""

    model_config = _STRICT_CONFIG

    source_summary: str = Field(default="")
    existing_catalog_hits: list[CatalogHitOutput] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    credential_gap_proposals: list[CredentialGapProposalOutput] = Field(default_factory=list)


class DraftOutput(BaseModel):
    """Structured output for the proposal_drafter role."""

    model_config = _STRICT_CONFIG

    proposal: DraftProposalOutput | None = None
    enum_gap_proposals: list[EnumGapProposalOutput] = Field(default_factory=list)
    harmonisation_items: list[HarmonisationItemOutput] = Field(default_factory=list)
    suggest_human_apply: list[SuggestHumanApplyItemOutput] = Field(default_factory=list)


class ReviewerOutput(BaseModel):
    """Structured output for governance and data-correctness reviewer roles."""

    model_config = _STRICT_CONFIG

    findings: list[str] = Field(default_factory=list)
    bounce_to_drafter: bool = False


class ApprovalOutput(BaseModel):
    """Structured output for the approval_parser role."""

    model_config = _STRICT_CONFIG

    edit_instructions: str = Field(default="")


class ExtractionModeOutput(BaseModel):
    """Structured output for ambiguous extraction-mode classification."""

    model_config = _STRICT_CONFIG

    extraction_mode: Literal["config_only", "custom_python"] = "config_only"
    rationale: str = Field(default="")


class TestReviewOutput(BaseModel):
    """Structured output for the test_reviewer role."""

    model_config = _STRICT_CONFIG

    summary: str = Field(default="")
    passed: bool = True


__all__ = [
    "ApprovalOutput",
    "CatalogHitOutput",
    "CredentialGapProposalOutput",
    "DraftOutput",
    "DraftProposalOutput",
    "ExtractionModeOutput",
    "ResearchOutput",
    "ReviewerOutput",
    "TestReviewOutput",
]
