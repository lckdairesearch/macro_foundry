"""Ingestion-domain Pydantic schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from macro_foundry.enums import FeedMethod
from macro_foundry.schemas._base import SchemaModel, TimestampedReadSchema


class IngestionFeedBase(SchemaModel):
    """Shared ingestion-feed fields."""

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

    feed_method: FeedMethod | None = None
    endpoint_url: str | None = None
    request_params: dict[str, Any] | None = None
    file_path_pattern: str | None = None
    response_mapping: dict[str, Any] | None = None
    cron_schedule: str | None = None
    is_active: bool | None = None


class IngestionFeedRead(TimestampedReadSchema, IngestionFeedBase):
    """API read model for an ingestion feed."""


class IngestionFeedMemberBase(SchemaModel):
    """Shared ingestion-feed-member fields."""

    ingestion_feed_id: UUID
    series_source_id: UUID
    selector_type: str
    selector_config: dict[str, Any] | None = None
    execution_order: int | None = None
    is_active: bool


class IngestionFeedMemberCreate(IngestionFeedMemberBase):
    """Payload for creating an ingestion feed member."""


class IngestionFeedMemberUpdate(SchemaModel):
    """PATCH payload for an ingestion feed member."""

    ingestion_feed_id: UUID | None = None
    series_source_id: UUID | None = None
    selector_type: str | None = None
    selector_config: dict[str, Any] | None = None
    execution_order: int | None = None
    is_active: bool | None = None


class IngestionFeedMemberRead(TimestampedReadSchema, IngestionFeedMemberBase):
    """API read model for an ingestion feed member."""


__all__ = [
    "IngestionFeedBase",
    "IngestionFeedCreate",
    "IngestionFeedMemberBase",
    "IngestionFeedMemberCreate",
    "IngestionFeedMemberRead",
    "IngestionFeedMemberUpdate",
    "IngestionFeedRead",
    "IngestionFeedUpdate",
]
