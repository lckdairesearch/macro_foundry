"""Run-log Pydantic schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from macro_foundry.enums import (
    ComputationRunStatus,
    ComputationTriggeredBy,
    IngestionRunStatus,
    IngestionTriggeredBy,
    InputVintagePolicy,
    OutputMode,
)
from macro_foundry.schemas._base import CreatedAtReadSchema, SchemaModel


class IngestionRunLogBase(SchemaModel):
    """Shared ingestion-run-log fields."""

    ingestion_feed_id: UUID
    started_at: datetime
    finished_at: datetime | None = None
    status: IngestionRunStatus
    rows_fetched: int | None = None
    rows_inserted: int | None = None
    rows_skipped: int | None = None
    error_message: str | None = None
    triggered_by: IngestionTriggeredBy
    code_version: str | None = None
    parameters: dict[str, Any] | None = None
    notes: str | None = None


class IngestionRunLogCreate(IngestionRunLogBase):
    """Payload for creating an ingestion run log."""


class IngestionRunLogUpdate(SchemaModel):
    """PATCH payload for an ingestion run log."""

    ingestion_feed_id: UUID | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: IngestionRunStatus | None = None
    rows_fetched: int | None = None
    rows_inserted: int | None = None
    rows_skipped: int | None = None
    error_message: str | None = None
    triggered_by: IngestionTriggeredBy | None = None
    code_version: str | None = None
    parameters: dict[str, Any] | None = None
    notes: str | None = None


class IngestionRunLogRead(CreatedAtReadSchema, IngestionRunLogBase):
    """API read model for an ingestion run log."""


class IngestionRunLogMemberBase(SchemaModel):
    """Shared member-level ingestion-run outcome fields."""

    ingestion_run_log_id: UUID
    ingestion_feed_member_id: UUID
    status: IngestionRunStatus
    rows_fetched: int | None = None
    rows_inserted: int | None = None
    rows_skipped: int | None = None
    error_message: str | None = None
    diagnostics: dict[str, Any] | None = None
    notes: str | None = None


class IngestionRunLogMemberCreate(IngestionRunLogMemberBase):
    """Payload for creating an ingestion run-log member outcome."""


class IngestionRunLogMemberUpdate(SchemaModel):
    """PATCH payload for an ingestion run-log member outcome."""

    ingestion_run_log_id: UUID | None = None
    ingestion_feed_member_id: UUID | None = None
    status: IngestionRunStatus | None = None
    rows_fetched: int | None = None
    rows_inserted: int | None = None
    rows_skipped: int | None = None
    error_message: str | None = None
    diagnostics: dict[str, Any] | None = None
    notes: str | None = None


class IngestionRunLogMemberRead(CreatedAtReadSchema, IngestionRunLogMemberBase):
    """API read model for an ingestion run-log member outcome."""


class ComputationRunLogBase(SchemaModel):
    """Shared computation-run-log fields."""

    derived_series_id: UUID
    started_at: datetime
    finished_at: datetime | None = None
    status: ComputationRunStatus
    rows_computed: int | None = None
    rows_inserted: int | None = None
    rows_updated: int | None = None
    rows_skipped: int | None = None
    error_message: str | None = None
    triggered_by: ComputationTriggeredBy
    code_version: str | None = None
    input_vintage_policy: InputVintagePolicy | None = None
    input_vintage_date: date | None = None
    parameters: dict[str, Any] | None = None
    output_mode: OutputMode | None = None
    notes: str | None = None


class ComputationRunLogCreate(ComputationRunLogBase):
    """Payload for creating a computation run log."""


class ComputationRunLogUpdate(SchemaModel):
    """PATCH payload for a computation run log."""

    derived_series_id: UUID | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: ComputationRunStatus | None = None
    rows_computed: int | None = None
    rows_inserted: int | None = None
    rows_updated: int | None = None
    rows_skipped: int | None = None
    error_message: str | None = None
    triggered_by: ComputationTriggeredBy | None = None
    code_version: str | None = None
    input_vintage_policy: InputVintagePolicy | None = None
    input_vintage_date: date | None = None
    parameters: dict[str, Any] | None = None
    output_mode: OutputMode | None = None
    notes: str | None = None


class ComputationRunLogRead(CreatedAtReadSchema, ComputationRunLogBase):
    """API read model for a computation run log."""


__all__ = [
    "ComputationRunLogBase",
    "ComputationRunLogCreate",
    "ComputationRunLogRead",
    "ComputationRunLogUpdate",
    "IngestionRunLogBase",
    "IngestionRunLogCreate",
    "IngestionRunLogMemberBase",
    "IngestionRunLogMemberCreate",
    "IngestionRunLogMemberRead",
    "IngestionRunLogMemberUpdate",
    "IngestionRunLogRead",
    "IngestionRunLogUpdate",
]
