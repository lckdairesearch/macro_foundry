"""Concept SQLAlchemy model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import TimestampedBase

if TYPE_CHECKING:
    from macro_foundry.models.series import SeriesFamily


class Concept(TimestampedBase):
    """Geography-neutral curated macro concept."""

    __tablename__ = "concepts"
    __table_args__ = (UniqueConstraint("code", name="uq_concepts_code"),)

    code: Mapped[str] = mapped_column(String(), nullable=False)
    name: Mapped[str] = mapped_column(String(), nullable=False)
    description: Mapped[str | None] = mapped_column(String(), nullable=True)

    series_families: Mapped[list["SeriesFamily"]] = relationship(
        "SeriesFamily",
        back_populates="concept",
        lazy="selectin",
        passive_deletes=True,
    )


__all__ = ["Concept"]
