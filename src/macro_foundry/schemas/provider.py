"""Provider-domain Pydantic schemas."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import Field

from macro_foundry.enums import AuthScheme, ProviderRole, ProviderType
from macro_foundry.schemas._base import SchemaModel, TimestampedReadSchema


class ProviderBase(SchemaModel):
    """Shared provider fields."""

    name: str
    alt_name: list[str] | None = None
    type: ProviderType
    homepage_url: str | None = None
    doc_url: str | None = None
    base_url: str | None = None
    credentials_ref: str | None = None
    auth_scheme: AuthScheme | None = None
    rate_limit_config: dict[str, Any] | None = None
    notes: str | None = None
    is_active: bool


class ProviderCreate(ProviderBase):
    """Payload for creating a provider."""


class ProviderUpdate(SchemaModel):
    """PATCH payload for a provider."""

    name: str | None = None
    alt_name: list[str] | None = None
    type: ProviderType | None = None
    homepage_url: str | None = None
    doc_url: str | None = None
    base_url: str | None = None
    credentials_ref: str | None = None
    auth_scheme: AuthScheme | None = None
    rate_limit_config: dict[str, Any] | None = None
    notes: str | None = None
    is_active: bool | None = None


class ProviderRead(TimestampedReadSchema, ProviderBase):
    """API read model for a provider."""


class ProviderCatalogBase(SchemaModel):
    """Shared provider-catalog fields."""

    provider_id: UUID
    name: str
    catalog_url: str | None = None
    doc_url: str | None = None
    notes: str | None = None
    is_placeholder: bool


class ProviderCatalogCreate(ProviderCatalogBase):
    """Payload for creating a provider catalog."""


class ProviderCatalogUpdate(SchemaModel):
    """PATCH payload for a provider catalog."""

    provider_id: UUID | None = None
    name: str | None = None
    catalog_url: str | None = None
    doc_url: str | None = None
    notes: str | None = None
    is_placeholder: bool | None = None


class ProviderCatalogRead(TimestampedReadSchema, ProviderCatalogBase):
    """API read model for a provider catalog."""


class SeriesSourceBase(SchemaModel):
    """Shared series-source fields."""

    series_id: UUID
    provider_catalog_id: UUID
    external_code: str | None = None
    external_name: str | None = None
    ref_url: str | None = None
    priority: int
    provider_role: ProviderRole
    value_transform: dict[str, Any] | None = None
    start_date: date | None = None
    end_date: date | None = None


class SeriesSourceCreate(SeriesSourceBase):
    """Payload for creating a series-source mapping."""


class SeriesSourceUpdate(SchemaModel):
    """PATCH payload for a series-source mapping."""

    series_id: UUID | None = None
    provider_catalog_id: UUID | None = None
    external_code: str | None = None
    external_name: str | None = None
    ref_url: str | None = None
    priority: int | None = None
    provider_role: ProviderRole | None = None
    value_transform: dict[str, Any] | None = None
    start_date: date | None = None
    end_date: date | None = None


class SeriesSourceRead(TimestampedReadSchema, SeriesSourceBase):
    """API read model for a series-source mapping."""


class ProviderCatalogReadDetail(ProviderCatalogRead):
    """Read model including same-domain source mappings."""

    series_sources: list[SeriesSourceRead] = Field(default_factory=list)


class ProviderReadDetail(ProviderRead):
    """Read model including same-domain catalog rows."""

    catalogs: list[ProviderCatalogRead] = Field(default_factory=list)


__all__ = [
    "ProviderBase",
    "ProviderCatalogBase",
    "ProviderCatalogCreate",
    "ProviderCatalogRead",
    "ProviderCatalogReadDetail",
    "ProviderCatalogUpdate",
    "ProviderCreate",
    "ProviderRead",
    "ProviderReadDetail",
    "ProviderUpdate",
    "SeriesSourceBase",
    "SeriesSourceCreate",
    "SeriesSourceRead",
    "SeriesSourceUpdate",
]
