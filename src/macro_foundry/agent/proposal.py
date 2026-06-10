"""DraftProposal and candidate row models for the onboarding agent."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, model_validator


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


__all__ = [
    "DraftConcept",
    "DraftFamily",
    "DraftFamilyMember",
    "DraftHierarchyEdge",
    "DraftIngestionFeed",
    "DraftProposal",
    "DraftSeries",
    "DraftSeriesSource",
    "HarmonisationItem",
    "ReferenceMetadata",
    "SuggestHumanApplyItem",
]
