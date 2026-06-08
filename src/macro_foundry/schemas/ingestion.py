"""Ingestion-domain Pydantic schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from macro_foundry.enums import FeedMethod
from macro_foundry.schemas._base import SchemaModel, TimestampedReadSchema


class IngestionFeedBase(SchemaModel):
    """Shared ingestion-feed fields."""

    series_source_id: UUID
    feed_method: FeedMethod
    endpoint_url: str | None = None
    request_params: dict[str, Any] | None = None
    file_path_pattern: str | None = None
    response_mapping: dict[str, Any] | None = None
    cron_schedule: str | None = None
    is_active: bool


class IngestionFeedCreate(IngestionFeedBase):
    """Payload for creating an ingestion feed."""


class IngestionFeedUpdate(SchemaModel):
    """PATCH payload for an ingestion feed."""

    series_source_id: UUID | None = None
    feed_method: FeedMethod | None = None
    endpoint_url: str | None = None
    request_params: dict[str, Any] | None = None
    file_path_pattern: str | None = None
    response_mapping: dict[str, Any] | None = None
    cron_schedule: str | None = None
    is_active: bool | None = None


class IngestionFeedRead(TimestampedReadSchema, IngestionFeedBase):
    """API read model for an ingestion feed."""


__all__ = [
    "IngestionFeedBase",
    "IngestionFeedCreate",
    "IngestionFeedRead",
    "IngestionFeedUpdate",
]
