"""Observation SQLAlchemy model."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import CreatedAtBase

if TYPE_CHECKING:
    from macro_foundry.models.run_log import ComputationRunLog, IngestionRunLog
    from macro_foundry.models.series import Series


class Observation(CreatedAtBase):
    """Vintage-aware observation row."""

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("series_id", "period_start", "vintage_date", name="uq_observations_series_period_vintage"),
        CheckConstraint("period_end >= period_start", name="ck_observations_period_bounds"),
    )

    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("series.id", ondelete="RESTRICT"),
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    vintage_date: Mapped[date] = mapped_column(Date, nullable=False)
    ingestion_run_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_run_logs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    computation_run_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("computation_run_logs.id", ondelete="RESTRICT"),
        nullable=True,
    )

    series: Mapped["Series"] = relationship(
        "Series",
        back_populates="observations",
        lazy="selectin",
    )
    ingestion_run_log: Mapped["IngestionRunLog | None"] = relationship(
        "IngestionRunLog",
        back_populates="observations",
        lazy="selectin",
    )
    computation_run_log: Mapped["ComputationRunLog | None"] = relationship(
        "ComputationRunLog",
        back_populates="observations",
        lazy="selectin",
    )


__all__ = ["Observation"]
