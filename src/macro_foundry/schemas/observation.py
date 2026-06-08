"""Observation-domain Pydantic schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import model_validator

from macro_foundry.schemas._base import CreatedAtReadSchema, SchemaModel


def _validate_period_bounds(period_start: date | None, period_end: date | None) -> None:
    if period_start is not None and period_end is not None and period_end < period_start:
        raise ValueError("period_end must be on or after period_start")


class ObservationBase(SchemaModel):
    """Shared observation fields."""

    series_id: UUID
    period_start: date
    period_end: date
    value: Decimal | None = None
    vintage_date: date
    ingestion_run_log_id: UUID | None = None
    computation_run_log_id: UUID | None = None


class ObservationCreate(ObservationBase):
    """Payload for creating an observation."""

    @model_validator(mode="after")
    def validate_period_bounds(self) -> Self:
        _validate_period_bounds(self.period_start, self.period_end)
        return self


class ObservationUpdate(SchemaModel):
    """PATCH payload for an observation."""

    series_id: UUID | None = None
    period_start: date | None = None
    period_end: date | None = None
    value: Decimal | None = None
    vintage_date: date | None = None
    ingestion_run_log_id: UUID | None = None
    computation_run_log_id: UUID | None = None

    @model_validator(mode="after")
    def validate_period_bounds(self) -> Self:
        if {"period_start", "period_end"}.issubset(self.model_fields_set):
            _validate_period_bounds(self.period_start, self.period_end)
        return self


class ObservationRead(CreatedAtReadSchema, ObservationBase):
    """API read model for an observation."""


__all__ = [
    "ObservationBase",
    "ObservationCreate",
    "ObservationRead",
    "ObservationUpdate",
]
