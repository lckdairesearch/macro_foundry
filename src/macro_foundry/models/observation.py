"""Observation SQLAlchemy model."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import CreatedAtBase
from macro_foundry.models._schema_policy import fk_uuid

if TYPE_CHECKING:
    from macro_foundry.models.run_log import ComputationRunLog, IngestionRunLogMember
    from macro_foundry.models.series import Series


class Observation(CreatedAtBase):
    """Vintage-aware observation row."""

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("series_id", "period_start", "vintage_date", name="uq_observations_series_period_vintage"),
        CheckConstraint("period_end >= period_start", name="ck_observations_period_bounds"),
    )

    series_id: Mapped[uuid.UUID] = fk_uuid(
        "series.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    vintage_date: Mapped[date] = mapped_column(Date, nullable=False)
    ingestion_run_log_member_id: Mapped[uuid.UUID | None] = fk_uuid(
        "ingestion_run_log_members.id",
        ondelete="RESTRICT",
        nullable=True,
    )
    computation_run_log_id: Mapped[uuid.UUID | None] = fk_uuid(
        "computation_run_logs.id",
        ondelete="RESTRICT",
        nullable=True,
    )

    series: Mapped["Series"] = relationship(
        "Series",
        back_populates="observations",
        lazy="selectin",
    )
    ingestion_run_log_member: Mapped["IngestionRunLogMember | None"] = relationship(
        "IngestionRunLogMember",
        back_populates="observations",
        lazy="selectin",
    )
    computation_run_log: Mapped["ComputationRunLog | None"] = relationship(
        "ComputationRunLog",
        back_populates="observations",
        lazy="selectin",
    )


__all__ = ["Observation"]
