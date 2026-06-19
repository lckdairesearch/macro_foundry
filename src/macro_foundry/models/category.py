"""Category-tree SQLAlchemy models (ADR 0025 §1, §2)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import TimestampedBase
from macro_foundry.enums import CategoryKind
from macro_foundry.models._schema_policy import enum_column, fk_uuid
from macro_foundry.models._vector import Vector

_EMBEDDING_DIMENSIONS = 1536


class Category(TimestampedBase):
    """A node in the single catalog tree: a browse topic or an attachable concept."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("code", name="uq_categories_code"),)

    code: Mapped[str] = mapped_column(String(), nullable=False)
    name: Mapped[str] = mapped_column(String(), nullable=False)
    description: Mapped[str | None] = mapped_column(String(), nullable=True)
    kind: Mapped[CategoryKind] = enum_column(
        "categories",
        "kind",
        CategoryKind,
        nullable=False,
    )
    # Populated for kind=concept; HNSW cosine index lives in the migration.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_EMBEDDING_DIMENSIONS), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(Text(), nullable=True)
    embedding_input_hash: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Edges where this node is the parent (its direct children).
    child_edges: Mapped[list["CategoryEdge"]] = relationship(
        "CategoryEdge",
        back_populates="parent_category",
        foreign_keys="CategoryEdge.parent_category_id",
        lazy="selectin",
        passive_deletes=True,
    )
    # The single edge where this node is the child (its parent). Roots have none.
    parent_edge: Mapped["CategoryEdge | None"] = relationship(
        "CategoryEdge",
        back_populates="child_category",
        foreign_keys="CategoryEdge.child_category_id",
        lazy="selectin",
        uselist=False,
        passive_deletes=True,
    )


class CategoryEdge(TimestampedBase):
    """A parent/child link in the strict category tree.

    `UNIQUE(child_category_id)` enforces a single parent per node (a tree). Roots
    carry no edge. Depth <= 3 is a curation convention, not a constraint.
    """

    __tablename__ = "category_edges"
    __table_args__ = (
        UniqueConstraint("child_category_id", name="uq_category_edges_child_category_id"),
        CheckConstraint(
            "parent_category_id != child_category_id",
            name="ck_category_edges_no_self_edge",
        ),
    )

    parent_category_id: Mapped[uuid.UUID] = fk_uuid(
        "categories.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    child_category_id: Mapped[uuid.UUID] = fk_uuid(
        "categories.id",
        ondelete="CASCADE",
        nullable=False,
    )
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    parent_category: Mapped["Category"] = relationship(
        "Category",
        back_populates="child_edges",
        foreign_keys=[parent_category_id],
        lazy="selectin",
    )
    child_category: Mapped["Category"] = relationship(
        "Category",
        back_populates="parent_edge",
        foreign_keys=[child_category_id],
        lazy="selectin",
    )


__all__ = ["Category", "CategoryEdge"]
