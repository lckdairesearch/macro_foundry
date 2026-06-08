"""Ingestion SQLAlchemy models."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import TimestampedBase
from macro_foundry.enums import FeedMethod
from macro_foundry.models._schema_policy import enum_column, fk_uuid

if TYPE_CHECKING:
    from macro_foundry.models.provider import SeriesSource
    from macro_foundry.models.run_log import IngestionRunLog


class IngestionFeed(TimestampedBase):
    """Runtime ingestion configuration for a series source."""

    __tablename__ = "ingestion_feeds"

    series_source_id: Mapped[uuid.UUID] = fk_uuid(
        "series_sources.id",
        ondelete="CASCADE",
        nullable=False,
    )
    feed_method: Mapped[FeedMethod] = enum_column(
        "ingestion_feeds",
        "feed_method",
        FeedMethod,
        nullable=False,
    )
    endpoint_url: Mapped[str | None] = mapped_column(String(), nullable=True)
    request_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    file_path_pattern: Mapped[str | None] = mapped_column(String(), nullable=True)
    response_mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    cron_schedule: Mapped[str | None] = mapped_column(String(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)

    series_source: Mapped["SeriesSource"] = relationship(
        "SeriesSource",
        back_populates="ingestion_feeds",
        lazy="selectin",
    )
    ingestion_run_logs: Mapped[list["IngestionRunLog"]] = relationship(
        "IngestionRunLog",
        back_populates="ingestion_feed",
        lazy="selectin",
        passive_deletes=True,
    )


__all__ = ["IngestionFeed"]
