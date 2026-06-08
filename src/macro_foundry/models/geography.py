"""Geography-domain SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, CheckConstraint, Date, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import TimestampedBase
from macro_foundry.enums import CodeStandard, GeographyType

if TYPE_CHECKING:
    from macro_foundry.models.series import Series, SeriesFamily


class Geography(TimestampedBase):
    """Canonical geography row from the V3 schema."""

    __tablename__ = "geographies"
    __table_args__ = (
        UniqueConstraint("code", name="uq_geographies_code"),
        CheckConstraint(
            "(type NOT IN ('subnational', 'subnational_region')) OR parent_geography_id IS NOT NULL",
            name="ck_geographies_type_requires_parent",
        ),
    )

    code: Mapped[str] = mapped_column(String(), nullable=False)
    name: Mapped[str] = mapped_column(String(), nullable=False)
    alt_name: Mapped[list[str] | None] = mapped_column(ARRAY(Text()), nullable=True)
    type: Mapped[GeographyType] = mapped_column(
        SAEnum(GeographyType, native_enum=False, name="ck_geographies_type", validate_strings=True),
        nullable=False,
    )
    code_standard: Mapped[CodeStandard] = mapped_column(
        SAEnum(CodeStandard, native_enum=False, name="ck_geographies_code_standard", validate_strings=True),
        nullable=False,
    )
    parent_geography_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("geographies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(String(), nullable=True)

    parent_geography: Mapped["Geography | None"] = relationship(
        "Geography",
        back_populates="child_geographies",
        foreign_keys=lambda: [Geography.parent_geography_id],
        remote_side=lambda: [Geography.id],
        lazy="selectin",
    )
    child_geographies: Mapped[list["Geography"]] = relationship(
        "Geography",
        back_populates="parent_geography",
        foreign_keys=lambda: [Geography.parent_geography_id],
        lazy="selectin",
        passive_deletes=True,
    )
    member_memberships: Mapped[list["GeographyMembership"]] = relationship(
        "GeographyMembership",
        back_populates="member_geography",
        foreign_keys="GeographyMembership.member_geography_id",
        lazy="selectin",
        passive_deletes=True,
    )
    group_memberships: Mapped[list["GeographyMembership"]] = relationship(
        "GeographyMembership",
        back_populates="group_geography",
        foreign_keys="GeographyMembership.group_geography_id",
        lazy="selectin",
        passive_deletes=True,
    )
    series: Mapped[list["Series"]] = relationship(
        "Series",
        back_populates="geography",
        lazy="selectin",
        passive_deletes=True,
    )
    series_families: Mapped[list["SeriesFamily"]] = relationship(
        "SeriesFamily",
        back_populates="geography",
        lazy="selectin",
        passive_deletes=True,
    )


class GeographyMembership(TimestampedBase):
    """Time-bounded geography membership row."""

    __tablename__ = "geography_memberships"

    member_geography_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("geographies.id", ondelete="CASCADE"),
        nullable=False,
    )
    group_geography_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("geographies.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    member_geography: Mapped["Geography"] = relationship(
        "Geography",
        back_populates="member_memberships",
        foreign_keys=[member_geography_id],
        lazy="selectin",
    )
    group_geography: Mapped["Geography"] = relationship(
        "Geography",
        back_populates="group_memberships",
        foreign_keys=[group_geography_id],
        lazy="selectin",
    )


__all__ = ["Geography", "GeographyMembership"]
