"""Run-log SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
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
from macro_foundry.models._schema_policy import enum_column, fk_uuid

if TYPE_CHECKING:
    from macro_foundry.models.derived import DerivedSeries
    from macro_foundry.models.ingestion import IngestionFeed, IngestionFeedMember
    from macro_foundry.models.observation import Observation


class IngestionRunLog(CreatedAtBase):
    """Append-only ingestion run audit row."""

    __tablename__ = "ingestion_run_logs"

    ingestion_feed_id: Mapped[uuid.UUID] = fk_uuid(
        "ingestion_feeds.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[IngestionRunStatus] = enum_column(
        "ingestion_run_logs",
        "status",
        IngestionRunStatus,
        nullable=False,
    )
    rows_fetched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_inserted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(), nullable=True)
    triggered_by: Mapped[IngestionTriggeredBy] = enum_column(
        "ingestion_run_logs",
        "triggered_by",
        IngestionTriggeredBy,
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
    member_logs: Mapped[list["IngestionRunLogMember"]] = relationship(
        "IngestionRunLogMember",
        back_populates="ingestion_run_log",
        lazy="selectin",
        passive_deletes=True,
    )


class IngestionRunLogMember(CreatedAtBase):
    """Append-only outcome for one attempted member inside a feed execution."""

    __tablename__ = "ingestion_run_log_members"
    __table_args__ = (
        UniqueConstraint(
            "ingestion_run_log_id",
            "ingestion_feed_member_id",
            name="uq_ingestion_run_log_members_run_member",
        ),
    )

    ingestion_run_log_id: Mapped[uuid.UUID] = fk_uuid(
        "ingestion_run_logs.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    ingestion_feed_member_id: Mapped[uuid.UUID] = fk_uuid(
        "ingestion_feed_members.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    status: Mapped[IngestionRunStatus] = enum_column(
        "ingestion_run_log_members",
        "status",
        IngestionRunStatus,
        nullable=False,
    )
    rows_fetched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_inserted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(), nullable=True)
    diagnostics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(), nullable=True)

    ingestion_run_log: Mapped["IngestionRunLog"] = relationship(
        "IngestionRunLog",
        back_populates="member_logs",
        lazy="selectin",
    )
    ingestion_feed_member: Mapped["IngestionFeedMember"] = relationship(
        "IngestionFeedMember",
        back_populates="run_logs",
        lazy="selectin",
    )
    observations: Mapped[list["Observation"]] = relationship(
        "Observation",
        back_populates="ingestion_run_log_member",
        lazy="selectin",
        passive_deletes=True,
    )


class ComputationRunLog(CreatedAtBase):
    """Append-only derived-series computation audit row."""

    __tablename__ = "computation_run_logs"

    derived_series_id: Mapped[uuid.UUID] = fk_uuid(
        "derived_series.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[ComputationRunStatus] = enum_column(
        "computation_run_logs",
        "status",
        ComputationRunStatus,
        nullable=False,
    )
    rows_computed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_inserted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_updated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(), nullable=True)
    triggered_by: Mapped[ComputationTriggeredBy] = enum_column(
        "computation_run_logs",
        "triggered_by",
        ComputationTriggeredBy,
        nullable=False,
    )
    code_version: Mapped[str | None] = mapped_column(String(), nullable=True)
    input_vintage_policy: Mapped[InputVintagePolicy | None] = enum_column(
        "computation_run_logs",
        "input_vintage_policy",
        InputVintagePolicy,
        nullable=True,
    )
    input_vintage_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    output_mode: Mapped[OutputMode | None] = enum_column(
        "computation_run_logs",
        "output_mode",
        OutputMode,
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


__all__ = ["ComputationRunLog", "IngestionRunLog", "IngestionRunLogMember"]
