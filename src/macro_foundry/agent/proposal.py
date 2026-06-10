"""DraftProposal and candidate row models for the onboarding agent."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class DraftConcept(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["new", "existing"]
    code: str
    name: str
    description: str | None = None


class DraftFamily(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["new", "existing"]
    code: str
    name: str
    concept_code: str
    geography_code: str
    description: str | None = None


class DraftSeries(BaseModel):
    model_config = ConfigDict(frozen=True)

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


class DraftSeriesSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_name: str
    external_code: str
    external_name: str | None = None
    provider_role: str = "primary_source"
    priority: int = 1


class DraftIngestionFeed(BaseModel):
    model_config = ConfigDict(frozen=True)

    selector_type: str
    selector_config: dict[str, Any] | None = None
    cron_schedule: str
    feed_method: str
    fetch_url: str | None = None
    is_active: bool = True


class DraftFamilyMember(BaseModel):
    model_config = ConfigDict(frozen=True)

    variant: str | None = None
    is_primary: bool = True


class DraftHierarchyEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    parent_series_code: str
    child_series_code: str
    edge_kind: str


class DraftProposal(BaseModel):
    model_config = ConfigDict(frozen=True)

    concept: DraftConcept
    family: DraftFamily
    series: DraftSeries
    source: DraftSeriesSource
    feed: DraftIngestionFeed
    family_member: DraftFamilyMember
    hierarchy_edges: tuple[DraftHierarchyEdge, ...] = ()


class ReferenceMetadata(BaseModel):
    """Cohort data gathered before draft_proposal; records empty cohorts explicitly."""

    model_config = ConfigDict(frozen=True)

    cohort_a: tuple[dict[str, Any], ...] = ()
    cohort_b: tuple[dict[str, Any], ...] = ()
    cohort_c: tuple[dict[str, Any], ...] = ()
    is_first_in_family: bool

    def __init__(self, **data: Any) -> None:
        for key in ("cohort_a", "cohort_b", "cohort_c"):
            if key in data and isinstance(data[key], list):
                data[key] = tuple(data[key])
        super().__init__(**data)


_FACTUAL_TRIGGERS = frozenset({"factual_incompleteness", "factual_error"})
_OUTLIER_TRIGGERS = frozenset({"family_outlier", "house_voice_outlier"})


class HarmonisationItem(BaseModel):
    """Evidence-bearing item proposing a prose update to an existing sibling."""

    model_config = ConfigDict(frozen=True)

    trigger: Literal["factual_incompleteness", "factual_error", "family_outlier", "house_voice_outlier"]
    target_series_code: str
    schema_field: str | None = None
    source_url: str | None = None
    cohort_members: list[str] | None = None
    shared_pattern: str | None = None
    divergence: str | None = None
    proposed_diff: str

    @model_validator(mode="after")
    def _require_evidence(self) -> "HarmonisationItem":
        if self.trigger in _FACTUAL_TRIGGERS:
            if not self.schema_field:
                raise ValueError("schema_field is required for factual triggers")
            if not self.source_url:
                raise ValueError("source_url is required for factual triggers")
        elif self.trigger in _OUTLIER_TRIGGERS:
            if not self.cohort_members:
                raise ValueError("cohort_members is required for outlier triggers")
            if not self.shared_pattern:
                raise ValueError("shared_pattern is required for outlier triggers")
        return self


class SuggestHumanApplyItem(BaseModel):
    """Propose-only field change that must be applied by a human operator."""

    model_config = ConfigDict(frozen=True)

    schema_field: str
    target_series_code: str | None = None
    current_value: str | None = None
    proposed_value: str
    rationale: str


class ProviderIdentity(BaseModel):
    """Credential-gap target provider identity."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["existing", "new"]
    existing_provider_id: str | None = None
    proposed_provider_name: str | None = None
    proposed_provider_homepage_url: str | None = None
    proposed_provider_doc_url: str | None = None

    @model_validator(mode="after")
    def _require_identity_fields(self) -> "ProviderIdentity":
        if self.kind == "existing" and not self.existing_provider_id:
            raise ValueError("existing_provider_id is required for existing provider identity")
        if self.kind == "new" and not self.proposed_provider_name:
            raise ValueError("proposed_provider_name is required for new provider identity")
        return self


class CredentialGapProposal(BaseModel):
    """Evidence-bearing request for operator credential provisioning."""

    model_config = ConfigDict(frozen=True)

    provider_identity: ProviderIdentity
    proposed_env_var_name: str
    proposed_auth_scheme: str
    inferred_rate_limit: dict[str, Any] | None = None
    evidence_url: str
    evidence_snippet: str
    rationale: str

    @model_validator(mode="after")
    def _require_evidence(self) -> "CredentialGapProposal":
        if not self.evidence_url.strip():
            raise ValueError("evidence_url is required")
        if not self.evidence_snippet.strip():
            raise ValueError("evidence_snippet is required")
        return self


class CredentialGapResolution(BaseModel):
    """Resolved credential-gap operator action."""

    model_config = ConfigDict(frozen=True)

    outcome: Literal["provisioned", "provisioned_renamed", "declined", "aborted"]
    provider_identity: ProviderIdentity | None = None
    applied_env_var_name: str | None = None
    applied_auth_scheme: str | None = None
    applied_rate_limit_config: dict[str, Any] | None = None
    operator_rationale: str | None = None
    resolved_at: datetime


__all__ = [
    "DraftConcept",
    "DraftFamily",
    "DraftFamilyMember",
    "DraftHierarchyEdge",
    "DraftIngestionFeed",
    "DraftProposal",
    "DraftSeries",
    "DraftSeriesSource",
    "CredentialGapProposal",
    "CredentialGapResolution",
    "HarmonisationItem",
    "ProviderIdentity",
    "ReferenceMetadata",
    "SuggestHumanApplyItem",
]
