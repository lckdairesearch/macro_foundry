"""Tag-domain Pydantic schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from macro_foundry.schemas._base import ReadSchema, SchemaModel, TimestampedReadSchema


class TagBase(SchemaModel):
    """Shared tag fields."""

    code: str
    name: str


class TagCreate(TagBase):
    """Payload for creating a tag."""


class TagUpdate(SchemaModel):
    """PATCH payload for a tag."""

    code: str | None = None
    name: str | None = None


class TagRead(TimestampedReadSchema, TagBase):
    """API read model for a tag."""


class SeriesTagBase(SchemaModel):
    """Shared series-tag junction fields."""

    series_id: UUID
    tag_id: UUID


class SeriesTagCreate(SeriesTagBase):
    """Payload for creating a series-tag link."""


class SeriesTagUpdate(SchemaModel):
    """PATCH payload for a series-tag link."""

    series_id: UUID | None = None
    tag_id: UUID | None = None


class SeriesTagRead(ReadSchema, SeriesTagBase):
    """API read model for a series-tag link."""


class TagReadDetail(TagRead):
    """Read model including attached series links."""

    series_tags: list[SeriesTagRead] = Field(default_factory=list)


__all__ = [
    "SeriesTagBase",
    "SeriesTagCreate",
    "SeriesTagRead",
    "SeriesTagUpdate",
    "TagBase",
    "TagCreate",
    "TagRead",
    "TagReadDetail",
    "TagUpdate",
]
