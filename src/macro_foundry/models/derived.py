"""Derived-series SQLAlchemy models."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import TimestampedBase
from macro_foundry.enums import ExecutionPolicy

if TYPE_CHECKING:
    from macro_foundry.models.run_log import ComputationRunLog
    from macro_foundry.models.series import Series


class DerivedSeries(TimestampedBase):
    """Derived-series metadata row."""

    __tablename__ = "derived_series"
    __table_args__ = (UniqueConstraint("series_id", name="uq_derived_series_series_id"),)

    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("series.id", ondelete="CASCADE"),
        nullable=False,
    )
    formula_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str] = mapped_column(String(), nullable=False)
    execution_policy: Mapped[ExecutionPolicy] = mapped_column(
        SAEnum(ExecutionPolicy, native_enum=False, name="ck_derived_series_execution_policy", validate_strings=True),
        nullable=False,
    )
    is_deterministic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_vintage_awareness: Mapped[bool] = mapped_column(Boolean, nullable=False)
    code_ref: Mapped[str | None] = mapped_column(String(), nullable=True)

    series: Mapped["Series"] = relationship(
        "Series",
        back_populates="derived_series",
        lazy="selectin",
    )
    derivation_inputs: Mapped[list["DerivationInput"]] = relationship(
        "DerivationInput",
        back_populates="derived_series",
        lazy="selectin",
        passive_deletes=True,
    )
    computation_run_logs: Mapped[list["ComputationRunLog"]] = relationship(
        "ComputationRunLog",
        back_populates="derived_series",
        lazy="selectin",
        passive_deletes=True,
    )


class DerivationInput(TimestampedBase):
    """Input-series registry for one derived series."""

    __tablename__ = "derivation_inputs"
    __table_args__ = (
        UniqueConstraint("derived_series_id", "input_series_id", name="uq_derivation_inputs_output_input"),
    )

    derived_series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("derived_series.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("series.id", ondelete="RESTRICT"),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(String(), nullable=True)

    derived_series: Mapped["DerivedSeries"] = relationship(
        "DerivedSeries",
        back_populates="derivation_inputs",
        lazy="selectin",
    )
    input_series: Mapped["Series"] = relationship(
        "Series",
        back_populates="derivation_inputs",
        foreign_keys=[input_series_id],
        lazy="selectin",
    )


__all__ = ["DerivationInput", "DerivedSeries"]
