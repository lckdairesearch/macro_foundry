"""Series-domain Pydantic schemas."""

from __future__ import annotations

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from macro_foundry.enums import (
    Frequency,
    Measure,
    MeasureHorizon,
    OriginType,
    PriceBasis,
    ReferenceKind,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.schemas._base import SchemaModel, TimestampedReadSchema
from macro_foundry.schemas.category import CategoryRead
from macro_foundry.schemas.geography import GeographyRead


def _validate_series_constraints(
    measure: Measure | None,
    measure_horizon: MeasureHorizon | None,
    unit_kind: UnitKind | None,
    currency_code: str | None,
) -> None:
    if measure == Measure.GROWTH and measure_horizon is None:
        raise ValueError("measure_horizon is required when measure is growth")
    if unit_kind == UnitKind.CURRENCY and currency_code is None:
        raise ValueError("currency_code is required when unit_kind is currency")


class SeriesBase(SchemaModel):
    """Shared series fields."""

    code: str
    name: str
    alt_name: list[str] | None = None
    description: str | None = None
    origin_type: OriginType
    category_id: UUID | None = None
    is_default: bool = False
    geography_id: UUID
    frequency: Frequency
    temporal_stock_flow: TemporalStockFlow
    unit_kind: UnitKind
    unit_scale: UnitScale
    unit_label: str | None = None
    price_basis: PriceBasis | None = None
    currency_code: str | None = None
    measure: Measure
    measure_horizon: MeasureHorizon | None = None
    annualized: bool
    seasonal_adjustment: SeasonalAdjustment
    reference_kind: ReferenceKind | None = None
    reference_year: int | None = None
    reference_label: str | None = None
    replaced_by_series_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool


class SeriesCreate(SeriesBase):
    """Payload for creating a series."""

    @model_validator(mode="after")
    def validate_series_constraints(self) -> Self:
        _validate_series_constraints(
            self.measure,
            self.measure_horizon,
            self.unit_kind,
            self.currency_code,
        )
        return self


class SeriesUpdate(SchemaModel):
    """PATCH payload for a series."""

    code: str | None = None
    name: str | None = None
    alt_name: list[str] | None = None
    description: str | None = None
    origin_type: OriginType | None = None
    category_id: UUID | None = None
    is_default: bool | None = None
    geography_id: UUID | None = None
    frequency: Frequency | None = None
    temporal_stock_flow: TemporalStockFlow | None = None
    unit_kind: UnitKind | None = None
    unit_scale: UnitScale | None = None
    unit_label: str | None = None
    price_basis: PriceBasis | None = None
    currency_code: str | None = None
    measure: Measure | None = None
    measure_horizon: MeasureHorizon | None = None
    annualized: bool | None = None
    seasonal_adjustment: SeasonalAdjustment | None = None
    reference_kind: ReferenceKind | None = None
    reference_year: int | None = None
    reference_label: str | None = None
    replaced_by_series_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_series_constraints(self) -> Self:
        if {"measure", "measure_horizon"}.issubset(self.model_fields_set):
            _validate_series_constraints(
                self.measure,
                self.measure_horizon,
                None,
                None,
            )
        if {"unit_kind", "currency_code"}.issubset(self.model_fields_set):
            _validate_series_constraints(
                None,
                None,
                self.unit_kind,
                self.currency_code,
            )
        return self


class SeriesRead(TimestampedReadSchema, SeriesBase):
    """API read model for a series."""


class SeriesSearchHit(SchemaModel):
    """Semantic-search wrapper for a series hit."""

    series: SeriesRead
    similarity: float


class SeriesReadDetail(SeriesRead):
    """Series read model including selected cross-domain relationships."""

    geography: GeographyRead
    # Lineage walked up `category_edges` from `series.category_id`, most-specific
    # first: element 0 is the attached `kind=concept` node, then each ancestor up
    # to the domain root (ADR 0025 §1). The topic of the series is `[1:]`. Empty
    # when the series carries no `category_id`.
    category_path: list[CategoryRead] = Field(default_factory=list)


class SeriesHierarchyEdgeBase(SchemaModel):
    """Shared fields for canonical series hierarchy edges."""

    parent_series_id: UUID
    child_series_id: UUID
    sort_order: int | None = None
    notes: str | None = None


class SeriesHierarchyEdgeCreate(SeriesHierarchyEdgeBase):
    """Payload for creating a canonical series hierarchy edge."""

    @model_validator(mode="after")
    def validate_no_self_edge(self) -> Self:
        if self.parent_series_id == self.child_series_id:
            raise ValueError("parent_series_id and child_series_id must differ")
        return self


class SeriesHierarchyEdgeUpdate(SchemaModel):
    """PATCH payload for a canonical series hierarchy edge."""

    parent_series_id: UUID | None = None
    child_series_id: UUID | None = None
    sort_order: int | None = None
    notes: str | None = None


class SeriesHierarchyEdgeRead(TimestampedReadSchema, SeriesHierarchyEdgeBase):
    """API read model for a canonical series hierarchy edge."""


__all__ = [
    "SeriesBase",
    "SeriesCreate",
    "SeriesHierarchyEdgeBase",
    "SeriesHierarchyEdgeCreate",
    "SeriesHierarchyEdgeRead",
    "SeriesHierarchyEdgeUpdate",
    "SeriesRead",
    "SeriesReadDetail",
    "SeriesSearchHit",
    "SeriesUpdate",
]
