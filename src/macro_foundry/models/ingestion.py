"""Ingestion SQLAlchemy models."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import TimestampedBase
from macro_foundry.enums import FeedMethod
from macro_foundry.models._schema_policy import enum_column, fk_uuid

if TYPE_CHECKING:
    from macro_foundry.models.provider import SeriesSource
    from macro_foundry.models.run_log import IngestionRunLog


class IngestionFeed(TimestampedBase):
    """Runtime ingestion configuration for one upstream request shape."""

    __tablename__ = "ingestion_feeds"

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

    members: Mapped[list["IngestionFeedMember"]] = relationship(
        "IngestionFeedMember",
        back_populates="ingestion_feed",
        lazy="selectin",
        passive_deletes=True,
    )
    ingestion_run_logs: Mapped[list["IngestionRunLog"]] = relationship(
        "IngestionRunLog",
        back_populates="ingestion_feed",
        lazy="selectin",
        passive_deletes=True,
    )


class IngestionFeedMember(TimestampedBase):
    """Per-series attachment and extraction selector for an ingestion feed."""

    __tablename__ = "ingestion_feed_members"
    __table_args__ = (
        UniqueConstraint("series_source_id", name="uq_ingestion_feed_members_series_source_id"),
    )

    ingestion_feed_id: Mapped[uuid.UUID] = fk_uuid(
        "ingestion_feeds.id",
        ondelete="CASCADE",
        nullable=False,
    )
    series_source_id: Mapped[uuid.UUID] = fk_uuid(
        "series_sources.id",
        ondelete="CASCADE",
        nullable=False,
    )
    selector_type: Mapped[str] = mapped_column(String(), nullable=False)
    selector_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    execution_order: Mapped[int | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)

    ingestion_feed: Mapped["IngestionFeed"] = relationship(
        "IngestionFeed",
        back_populates="members",
        lazy="selectin",
    )
    series_source: Mapped["SeriesSource"] = relationship(
        "SeriesSource",
        back_populates="ingestion_feed_members",
        lazy="selectin",
    )


__all__ = ["IngestionFeed", "IngestionFeedMember"]
