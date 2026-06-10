"""DraftProposal and candidate row models for the onboarding agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class DraftSeriesSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_code: str
    external_code: str
    external_name: str | None = None


class DraftIngestionFeed(BaseModel):
    model_config = ConfigDict(frozen=True)

    selector_type: str
    cron_schedule: str
    fetch_url: str | None = None


class DraftFamilyMember(BaseModel):
    model_config = ConfigDict(frozen=True)

    variant: str | None = None


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


__all__ = [
    "DraftConcept",
    "DraftFamily",
    "DraftFamilyMember",
    "DraftHierarchyEdge",
    "DraftIngestionFeed",
    "DraftProposal",
    "DraftSeries",
    "DraftSeriesSource",
]
