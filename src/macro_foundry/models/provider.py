"""Provider-domain SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import ARRAY, Boolean, Date, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import TimestampedBase
from macro_foundry.enums import ProviderRole, ProviderType
from macro_foundry.models._schema_policy import enum_column, fk_uuid

if TYPE_CHECKING:
    from macro_foundry.models.ingestion import IngestionFeed
    from macro_foundry.models.series import Series


class Provider(TimestampedBase):
    """External or internal data provider."""

    __tablename__ = "providers"
    __table_args__ = (UniqueConstraint("name", name="uq_providers_name"),)

    name: Mapped[str] = mapped_column(String(), nullable=False)
    alt_name: Mapped[list[str] | None] = mapped_column(ARRAY(Text()), nullable=True)
    type: Mapped[ProviderType] = enum_column(
        "providers",
        "type",
        ProviderType,
        nullable=False,
    )
    homepage_url: Mapped[str | None] = mapped_column(String(), nullable=True)
    doc_url: Mapped[str | None] = mapped_column(String(), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(), nullable=True)
    credentials_ref: Mapped[str | None] = mapped_column(String(), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)

    catalogs: Mapped[list["ProviderCatalog"]] = relationship(
        "ProviderCatalog",
        back_populates="provider",
        lazy="selectin",
        passive_deletes=True,
    )


class ProviderCatalog(TimestampedBase):
    """Provider sub-catalog row."""

    __tablename__ = "provider_catalogs"

    provider_id: Mapped[uuid.UUID] = fk_uuid(
        "providers.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(), nullable=False)
    catalog_url: Mapped[str | None] = mapped_column(String(), nullable=True)
    doc_url: Mapped[str | None] = mapped_column(String(), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(), nullable=True)
    is_placeholder: Mapped[bool] = mapped_column(Boolean, nullable=False)

    provider: Mapped["Provider"] = relationship(
        "Provider",
        back_populates="catalogs",
        lazy="selectin",
    )
    series_sources: Mapped[list["SeriesSource"]] = relationship(
        "SeriesSource",
        back_populates="provider_catalog",
        lazy="selectin",
        passive_deletes=True,
    )


class SeriesSource(TimestampedBase):
    """Mapping from a canonical series to one provider representation."""

    __tablename__ = "series_sources"
    __table_args__ = (
        UniqueConstraint("provider_catalog_id", "external_code", name="uq_series_sources_catalog_external_code"),
    )

    series_id: Mapped[uuid.UUID] = fk_uuid(
        "series.id",
        ondelete="CASCADE",
        nullable=False,
    )
    provider_catalog_id: Mapped[uuid.UUID] = fk_uuid(
        "provider_catalogs.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    external_code: Mapped[str] = mapped_column(String(), nullable=False)
    external_name: Mapped[str | None] = mapped_column(String(), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_role: Mapped[ProviderRole] = enum_column(
        "series_sources",
        "provider_role",
        ProviderRole,
        nullable=False,
    )
    value_transform: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    series: Mapped["Series"] = relationship(
        "Series",
        back_populates="series_sources",
        lazy="selectin",
    )
    provider_catalog: Mapped["ProviderCatalog"] = relationship(
        "ProviderCatalog",
        back_populates="series_sources",
        lazy="selectin",
    )
    ingestion_feeds: Mapped[list["IngestionFeed"]] = relationship(
        "IngestionFeed",
        back_populates="series_source",
        lazy="selectin",
        passive_deletes=True,
    )


__all__ = ["Provider", "ProviderCatalog", "SeriesSource"]
