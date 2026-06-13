"""Tag-domain SQLAlchemy models."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import Base, TimestampedBase

if TYPE_CHECKING:
    from macro_foundry.models.concept import Concept


class Tag(TimestampedBase):
    """Curated tag taxonomy row."""

    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("code", name="uq_tags_code"),)

    code: Mapped[str] = mapped_column(String(), nullable=False)
    name: Mapped[str] = mapped_column(String(), nullable=False)

    concept_tags: Mapped[list["ConceptTag"]] = relationship(
        "ConceptTag",
        back_populates="tag",
        lazy="selectin",
        passive_deletes=True,
    )


class ConceptTag(Base):
    """Concept-grain topical tag junction (ADR 0022)."""

    __tablename__ = "concept_tags"

    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )

    concept: Mapped["Concept"] = relationship(
        "Concept",
        back_populates="concept_tags",
        lazy="selectin",
    )
    tag: Mapped["Tag"] = relationship(
        "Tag",
        back_populates="concept_tags",
        lazy="selectin",
    )


__all__ = ["ConceptTag", "Tag"]
