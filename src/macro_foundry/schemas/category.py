"""Category-tree Pydantic schemas (ADR 0025 §1, §2)."""

from __future__ import annotations

from typing import Self
from uuid import UUID

from pydantic import model_validator

from macro_foundry.enums import CategoryKind
from macro_foundry.schemas._base import SchemaModel, TimestampedReadSchema


class CategoryBase(SchemaModel):
    """Shared category fields. The `embedding*` columns are internal, not exposed."""

    code: str
    name: str
    description: str | None = None
    kind: CategoryKind


class CategoryCreate(CategoryBase):
    """Payload for creating a category node."""


class CategoryUpdate(SchemaModel):
    """PATCH payload for a category node."""

    code: str | None = None
    name: str | None = None
    description: str | None = None
    kind: CategoryKind | None = None


class CategoryRead(TimestampedReadSchema, CategoryBase):
    """API read model for a category node."""


class CategoryEdgeBase(SchemaModel):
    """Shared fields for a parent/child link in the category tree."""

    parent_category_id: UUID
    child_category_id: UUID
    sort_order: int | None = None


class CategoryEdgeCreate(CategoryEdgeBase):
    """Payload for creating a category edge."""

    @model_validator(mode="after")
    def validate_no_self_edge(self) -> Self:
        if self.parent_category_id == self.child_category_id:
            raise ValueError("parent_category_id and child_category_id must differ")
        return self


class CategoryEdgeUpdate(SchemaModel):
    """PATCH payload for a category edge."""

    parent_category_id: UUID | None = None
    child_category_id: UUID | None = None
    sort_order: int | None = None


class CategoryEdgeRead(TimestampedReadSchema, CategoryEdgeBase):
    """API read model for a category edge."""


__all__ = [
    "CategoryBase",
    "CategoryCreate",
    "CategoryEdgeBase",
    "CategoryEdgeCreate",
    "CategoryEdgeRead",
    "CategoryEdgeUpdate",
    "CategoryRead",
    "CategoryUpdate",
]
