"""Series-domain Pydantic schemas."""

from __future__ import annotations

from datetime import date, datetime
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
from macro_foundry.schemas._base import ReadSchema, SchemaModel, TimestampedReadSchema
from macro_foundry.schemas.geography import GeographyRead
from macro_foundry.schemas.tag import TagRead


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
    description: str | None = None
    origin_type: OriginType
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
    description: str | None = None
    origin_type: OriginType | None = None
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


class SeriesReadDetail(SeriesRead):
    """Series read model including selected cross-domain relationships."""

    geography: GeographyRead
    tags: list[TagRead] = Field(default_factory=list)


class SeriesFamilyBase(SchemaModel):
    """Shared series-family fields."""

    code: str
    name: str
    description: str | None = None
    concept_id: UUID
    geography_id: UUID


class SeriesFamilyCreate(SeriesFamilyBase):
    """Payload for creating a series family."""


class SeriesFamilyUpdate(SchemaModel):
    """PATCH payload for a series family."""

    code: str | None = None
    name: str | None = None
    description: str | None = None
    concept_id: UUID | None = None
    geography_id: UUID | None = None


class SeriesFamilyRead(TimestampedReadSchema, SeriesFamilyBase):
    """API read model for a series family."""


class SeriesFamilyMemberBase(SchemaModel):
    """Shared series-family-member fields."""

    family_id: UUID
    series_id: UUID
    variant: str | None = None
    is_primary: bool


class SeriesFamilyMemberCreate(SeriesFamilyMemberBase):
    """Payload for creating a family membership."""


class SeriesFamilyMemberUpdate(SchemaModel):
    """PATCH payload for a family membership."""

    family_id: UUID | None = None
    series_id: UUID | None = None
    variant: str | None = None
    is_primary: bool | None = None


class SeriesFamilyMemberRead(ReadSchema, SeriesFamilyMemberBase):
    """API read model for a family membership."""

    created_at: datetime
    updated_at: datetime


class SeriesFamilyReadDetail(SeriesFamilyRead):
    """Read model including same-domain family members."""

    members: list[SeriesFamilyMemberRead] = Field(default_factory=list)


__all__ = [
    "SeriesBase",
    "SeriesCreate",
    "SeriesFamilyBase",
    "SeriesFamilyCreate",
    "SeriesFamilyMemberBase",
    "SeriesFamilyMemberCreate",
    "SeriesFamilyMemberRead",
    "SeriesFamilyMemberUpdate",
    "SeriesFamilyRead",
    "SeriesFamilyReadDetail",
    "SeriesFamilyUpdate",
    "SeriesRead",
    "SeriesReadDetail",
    "SeriesUpdate",
]
