"""Derived-series Pydantic schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from macro_foundry.enums import ExecutionPolicy
from macro_foundry.schemas._base import SchemaModel, TimestampedReadSchema


class DerivedSeriesBase(SchemaModel):
    """Shared derived-series fields."""

    series_id: UUID
    formula_config: dict[str, Any] | None = None
    description: str
    execution_policy: ExecutionPolicy
    is_deterministic: bool
    requires_vintage_awareness: bool
    code_ref: str | None = None


class DerivedSeriesCreate(DerivedSeriesBase):
    """Payload for creating derived-series metadata."""


class DerivedSeriesUpdate(SchemaModel):
    """PATCH payload for derived-series metadata."""

    series_id: UUID | None = None
    formula_config: dict[str, Any] | None = None
    description: str | None = None
    execution_policy: ExecutionPolicy | None = None
    is_deterministic: bool | None = None
    requires_vintage_awareness: bool | None = None
    code_ref: str | None = None


class DerivedSeriesRead(TimestampedReadSchema, DerivedSeriesBase):
    """API read model for derived-series metadata."""


class DerivationInputBase(SchemaModel):
    """Shared derivation-input fields."""

    derived_series_id: UUID
    input_series_id: UUID
    notes: str | None = None


class DerivationInputCreate(DerivationInputBase):
    """Payload for creating a derivation input."""


class DerivationInputUpdate(SchemaModel):
    """PATCH payload for a derivation input."""

    derived_series_id: UUID | None = None
    input_series_id: UUID | None = None
    notes: str | None = None


class DerivationInputRead(TimestampedReadSchema, DerivationInputBase):
    """API read model for a derivation input."""


class DerivedSeriesReadDetail(DerivedSeriesRead):
    """Read model including same-domain input rows."""

    derivation_inputs: list[DerivationInputRead] = Field(default_factory=list)


__all__ = [
    "DerivedSeriesBase",
    "DerivedSeriesCreate",
    "DerivedSeriesRead",
    "DerivedSeriesReadDetail",
    "DerivedSeriesUpdate",
    "DerivationInputBase",
    "DerivationInputCreate",
    "DerivationInputRead",
    "DerivationInputUpdate",
]
