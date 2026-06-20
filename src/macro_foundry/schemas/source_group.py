"""Provider source-group Pydantic schemas (ADR 0025 §4)."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from macro_foundry.enums import SourceGroupType
from macro_foundry.schemas._base import SchemaModel, TimestampedReadSchema


class SourceGroupBase(SchemaModel):
    """Shared fields for a provider publication unit."""

    provider_catalog_id: UUID
    parent_group_id: UUID | None = None
    group_type: SourceGroupType
    code: str | None = None
    name: str
    source_url: str | None = None
    notes: str | None = None


class SourceGroupCreate(SourceGroupBase):
    """Payload for creating a source group."""


class SourceGroupUpdate(SchemaModel):
    """PATCH payload for a source group."""

    provider_catalog_id: UUID | None = None
    parent_group_id: UUID | None = None
    group_type: SourceGroupType | None = None
    code: str | None = None
    name: str | None = None
    source_url: str | None = None
    notes: str | None = None


class SourceGroupRead(TimestampedReadSchema, SourceGroupBase):
    """API read model for a source group."""


class SourceGroupMemberBase(SchemaModel):
    """Shared fields for a source-group membership link."""

    source_group_id: UUID
    series_source_id: UUID
    row_label: str | None = None
    sort_order: int | None = None


class SourceGroupMemberCreate(SourceGroupMemberBase):
    """Payload for creating a source-group membership."""


class SourceGroupMemberUpdate(SchemaModel):
    """PATCH payload for a source-group membership."""

    source_group_id: UUID | None = None
    series_source_id: UUID | None = None
    row_label: str | None = None
    sort_order: int | None = None


class SourceGroupMemberRead(TimestampedReadSchema, SourceGroupMemberBase):
    """API read model for a source-group membership."""


class SourceGroupReadDetail(SourceGroupRead):
    """Read model including same-domain membership rows."""

    members: list[SourceGroupMemberRead] = Field(default_factory=list)


__all__ = [
    "SourceGroupBase",
    "SourceGroupCreate",
    "SourceGroupMemberBase",
    "SourceGroupMemberCreate",
    "SourceGroupMemberRead",
    "SourceGroupMemberUpdate",
    "SourceGroupRead",
    "SourceGroupReadDetail",
    "SourceGroupUpdate",
]
