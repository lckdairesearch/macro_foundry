"""Concept-domain Pydantic schemas."""

from __future__ import annotations

from macro_foundry.schemas._base import SchemaModel, TimestampedReadSchema


class ConceptBase(SchemaModel):
    """Shared concept fields."""

    code: str
    name: str
    description: str | None = None


class ConceptCreate(ConceptBase):
    """Payload for creating a concept."""


class ConceptUpdate(SchemaModel):
    """PATCH payload for a concept."""

    code: str | None = None
    name: str | None = None
    description: str | None = None


class ConceptRead(TimestampedReadSchema, ConceptBase):
    """API read model for a concept."""


class ConceptSearchHit(SchemaModel):
    """Semantic-search wrapper for a concept hit."""

    concept: ConceptRead
    similarity: float


__all__ = [
    "ConceptBase",
    "ConceptCreate",
    "ConceptRead",
    "ConceptSearchHit",
    "ConceptUpdate",
]
