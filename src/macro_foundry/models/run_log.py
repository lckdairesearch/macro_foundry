"""Run-log SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import CreatedAtBase
from macro_foundry.enums import (
    ComputationRunStatus,
    ComputationTriggeredBy,
    IngestionRunStatus,
    IngestionTriggeredBy,
    InputVintagePolicy,
    OutputMode,
)

if TYPE_CHECKING:
    from macro_foundry.models.derived import DerivedSeries
    from macro_foundry.models.ingestion import IngestionFeed
    from macro_foundry.models.observation import Observation


class IngestionRunLog(CreatedAtBase):
    """Append-only ingestion run audit row."""

    __tablename__ = "ingestion_run_logs"

    ingestion_feed_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_feeds.id", ondelete="RESTRICT"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[IngestionRunStatus] = mapped_column(
        SAEnum(IngestionRunStatus, native_enum=False, name="ck_ingestion_run_logs_status", validate_strings=True),
        nullable=False,
    )
    rows_fetched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_inserted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(), nullable=True)
    triggered_by: Mapped[IngestionTriggeredBy] = mapped_column(
        SAEnum(
            IngestionTriggeredBy,
            native_enum=False,
            name="ck_ingestion_run_logs_triggered_by",
            validate_strings=True,
        ),
        nullable=False,
    )
    code_version: Mapped[str | None] = mapped_column(String(), nullable=True)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(), nullable=True)

    ingestion_feed: Mapped["IngestionFeed"] = relationship(
        "IngestionFeed",
        back_populates="ingestion_run_logs",
        lazy="selectin",
    )
    observations: Mapped[list["Observation"]] = relationship(
        "Observation",
        back_populates="ingestion_run_log",
        lazy="selectin",
        passive_deletes=True,
    )


class ComputationRunLog(CreatedAtBase):
    """Append-only derived-series computation audit row."""

    __tablename__ = "computation_run_logs"

    derived_series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("derived_series.id", ondelete="RESTRICT"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[ComputationRunStatus] = mapped_column(
        SAEnum(
            ComputationRunStatus,
            native_enum=False,
            name="ck_computation_run_logs_status",
            validate_strings=True,
        ),
        nullable=False,
    )
    rows_computed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_inserted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_updated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(), nullable=True)
    triggered_by: Mapped[ComputationTriggeredBy] = mapped_column(
        SAEnum(
            ComputationTriggeredBy,
            native_enum=False,
            name="ck_computation_run_logs_triggered_by",
            validate_strings=True,
        ),
        nullable=False,
    )
    code_version: Mapped[str | None] = mapped_column(String(), nullable=True)
    input_vintage_policy: Mapped[InputVintagePolicy | None] = mapped_column(
        SAEnum(
            InputVintagePolicy,
            native_enum=False,
            name="ck_computation_run_logs_input_vintage_policy",
            validate_strings=True,
        ),
        nullable=True,
    )
    input_vintage_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_mode: Mapped[OutputMode | None] = mapped_column(
        SAEnum(
            OutputMode,
            native_enum=False,
            name="ck_computation_run_logs_output_mode",
            validate_strings=True,
        ),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(String(), nullable=True)

    derived_series: Mapped["DerivedSeries"] = relationship(
        "DerivedSeries",
        back_populates="computation_run_logs",
        lazy="selectin",
    )
    observations: Mapped[list["Observation"]] = relationship(
        "Observation",
        back_populates="computation_run_log",
        lazy="selectin",
        passive_deletes=True,
    )


__all__ = ["ComputationRunLog", "IngestionRunLog"]
