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


class ConceptTagBase(SchemaModel):
    """Shared concept-tag junction fields."""

    concept_id: UUID
    tag_id: UUID


class ConceptTagCreate(ConceptTagBase):
    """Payload for creating a concept-tag link."""


class ConceptTagUpdate(SchemaModel):
    """PATCH payload for a concept-tag link."""

    concept_id: UUID | None = None
    tag_id: UUID | None = None


class ConceptTagRead(ReadSchema, ConceptTagBase):
    """API read model for a concept-tag link."""


class TagReadDetail(TagRead):
    """Read model including attached concept links."""

    concept_tags: list[ConceptTagRead] = Field(default_factory=list)


__all__ = [
    "ConceptTagBase",
    "ConceptTagCreate",
    "ConceptTagRead",
    "ConceptTagUpdate",
    "TagBase",
    "TagCreate",
    "TagRead",
    "TagReadDetail",
    "TagUpdate",
]
