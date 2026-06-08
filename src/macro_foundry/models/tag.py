"""Tag-domain SQLAlchemy models."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import Base, TimestampedBase

if TYPE_CHECKING:
    from macro_foundry.models.series import Series


class Tag(TimestampedBase):
    """Curated tag taxonomy row."""

    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("name", name="uq_tags_name"),)

    name: Mapped[str] = mapped_column(String(), nullable=False)

    series_tags: Mapped[list["SeriesTag"]] = relationship(
        "SeriesTag",
        back_populates="tag",
        lazy="selectin",
        passive_deletes=True,
    )


class SeriesTag(Base):
    """Canonical V3 series-tag junction table with a composite primary key."""

    __tablename__ = "series_tags"

    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("series.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )

    series: Mapped["Series"] = relationship(
        "Series",
        back_populates="series_tags",
        lazy="selectin",
    )
    tag: Mapped["Tag"] = relationship(
        "Tag",
        back_populates="series_tags",
        lazy="selectin",
    )


__all__ = ["SeriesTag", "Tag"]
