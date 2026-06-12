"""Series-domain SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import Base, TimestampedBase
from macro_foundry.enums import (
    Frequency,
    Measure,
    MeasureHorizon,
    OriginType,
    PriceBasis,
    ReferenceKind,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.models._schema_policy import enum_column, fk_uuid

if TYPE_CHECKING:
    from macro_foundry.models.concept import Concept
    from macro_foundry.models.derived import DerivationInput, DerivedSeries
    from macro_foundry.models.geography import Geography
    from macro_foundry.models.observation import Observation
    from macro_foundry.models.provider import SeriesSource
    from macro_foundry.models.tag import SeriesTag


class Series(TimestampedBase):
    """Canonical macro series definition."""

    __tablename__ = "series"
    __table_args__ = (
        UniqueConstraint("code", name="uq_series_code"),
        UniqueConstraint("replaced_by_series_id", name="uq_series_replaced_by_series_id"),
        CheckConstraint(
            "(measure != 'growth') OR measure_horizon IS NOT NULL",
            name="ck_series_growth_requires_horizon",
        ),
        CheckConstraint(
            "(unit_kind != 'currency') OR currency_code IS NOT NULL",
            name="ck_series_currency_requires_code",
        ),
    )

    code: Mapped[str] = mapped_column(String(), nullable=False)
    name: Mapped[str] = mapped_column(String(), nullable=False)
    alt_name: Mapped[list[str] | None] = mapped_column(ARRAY(Text()), nullable=True)
    description: Mapped[str | None] = mapped_column(String(), nullable=True)
    origin_type: Mapped[OriginType] = enum_column(
        "series",
        "origin_type",
        OriginType,
        nullable=False,
    )
    geography_id: Mapped[uuid.UUID] = fk_uuid(
        "geographies.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    frequency: Mapped[Frequency] = enum_column(
        "series",
        "frequency",
        Frequency,
        nullable=False,
    )
    temporal_stock_flow: Mapped[TemporalStockFlow] = enum_column(
        "series",
        "temporal_stock_flow",
        TemporalStockFlow,
        nullable=False,
    )
    unit_kind: Mapped[UnitKind] = enum_column(
        "series",
        "unit_kind",
        UnitKind,
        nullable=False,
    )
    unit_scale: Mapped[UnitScale] = enum_column(
        "series",
        "unit_scale",
        UnitScale,
        nullable=False,
    )
    unit_label: Mapped[str | None] = mapped_column(String(), nullable=True)
    price_basis: Mapped[PriceBasis | None] = enum_column(
        "series",
        "price_basis",
        PriceBasis,
        nullable=True,
    )
    currency_code: Mapped[str | None] = mapped_column(String(), nullable=True)
    measure: Mapped[Measure] = enum_column(
        "series",
        "measure",
        Measure,
        nullable=False,
    )
    measure_horizon: Mapped[MeasureHorizon | None] = enum_column(
        "series",
        "measure_horizon",
        MeasureHorizon,
        nullable=True,
    )
    annualized: Mapped[bool] = mapped_column(Boolean, nullable=False)
    seasonal_adjustment: Mapped[SeasonalAdjustment] = enum_column(
        "series",
        "seasonal_adjustment",
        SeasonalAdjustment,
        nullable=False,
    )
    reference_kind: Mapped[ReferenceKind | None] = enum_column(
        "series",
        "reference_kind",
        ReferenceKind,
        nullable=True,
    )
    reference_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_label: Mapped[str | None] = mapped_column(String(), nullable=True)
    replaced_by_series_id: Mapped[uuid.UUID | None] = fk_uuid(
        "series.id",
        ondelete="RESTRICT",
        nullable=True,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)

    geography: Mapped["Geography"] = relationship(
        "Geography",
        back_populates="series",
        lazy="selectin",
    )
    replaced_by_series: Mapped["Series | None"] = relationship(
        "Series",
        back_populates="replaces_series",
        foreign_keys=lambda: [Series.replaced_by_series_id],
        remote_side=lambda: [Series.id],
        lazy="selectin",
        uselist=False,
    )
    replaces_series: Mapped["Series | None"] = relationship(
        "Series",
        back_populates="replaced_by_series",
        foreign_keys=lambda: [Series.replaced_by_series_id],
        lazy="selectin",
        uselist=False,
    )
    series_tags: Mapped[list["SeriesTag"]] = relationship(
        "SeriesTag",
        back_populates="series",
        lazy="selectin",
        passive_deletes=True,
    )
    family_member: Mapped["SeriesFamilyMember | None"] = relationship(
        "SeriesFamilyMember",
        back_populates="series",
        lazy="selectin",
        passive_deletes=True,
        uselist=False,
    )
    series_sources: Mapped[list["SeriesSource"]] = relationship(
        "SeriesSource",
        back_populates="series",
        lazy="selectin",
        passive_deletes=True,
    )
    derived_series: Mapped["DerivedSeries | None"] = relationship(
        "DerivedSeries",
        back_populates="series",
        lazy="selectin",
        passive_deletes=True,
        uselist=False,
    )
    observations: Mapped[list["Observation"]] = relationship(
        "Observation",
        back_populates="series",
        lazy="selectin",
        passive_deletes=True,
    )
    derivation_inputs: Mapped[list["DerivationInput"]] = relationship(
        "DerivationInput",
        back_populates="input_series",
        foreign_keys="DerivationInput.input_series_id",
        lazy="selectin",
        passive_deletes=True,
    )
    child_hierarchy_edges: Mapped[list["SeriesHierarchyEdge"]] = relationship(
        "SeriesHierarchyEdge",
        back_populates="parent_series",
        foreign_keys="SeriesHierarchyEdge.parent_series_id",
        lazy="selectin",
        passive_deletes=True,
    )
    parent_hierarchy_edges: Mapped[list["SeriesHierarchyEdge"]] = relationship(
        "SeriesHierarchyEdge",
        back_populates="child_series",
        foreign_keys="SeriesHierarchyEdge.child_series_id",
        lazy="selectin",
        passive_deletes=True,
    )


class SeriesHierarchyEdge(TimestampedBase):
    """Canonical parent-child edge between real series rows."""

    __tablename__ = "series_hierarchy_edges"
    __table_args__ = (
        UniqueConstraint("parent_series_id", "child_series_id", name="uq_series_hierarchy_edges_parent_child"),
        CheckConstraint(
            "parent_series_id != child_series_id",
            name="ck_series_hierarchy_edges_no_self_edge",
        ),
    )

    parent_series_id: Mapped[uuid.UUID] = fk_uuid(
        "series.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    child_series_id: Mapped[uuid.UUID] = fk_uuid(
        "series.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(), nullable=True)

    parent_series: Mapped["Series"] = relationship(
        "Series",
        back_populates="child_hierarchy_edges",
        foreign_keys=[parent_series_id],
        lazy="selectin",
    )
    child_series: Mapped["Series"] = relationship(
        "Series",
        back_populates="parent_hierarchy_edges",
        foreign_keys=[child_series_id],
        lazy="selectin",
    )


class SeriesFamily(TimestampedBase):
    """Series family grouping one concept and one geography."""

    __tablename__ = "series_families"
    __table_args__ = (UniqueConstraint("code", name="uq_series_families_code"),)

    code: Mapped[str] = mapped_column(String(), nullable=False)
    name: Mapped[str] = mapped_column(String(), nullable=False)
    description: Mapped[str | None] = mapped_column(String(), nullable=True)
    concept_id: Mapped[uuid.UUID] = fk_uuid(
        "concepts.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    geography_id: Mapped[uuid.UUID] = fk_uuid(
        "geographies.id",
        ondelete="RESTRICT",
        nullable=False,
    )

    concept: Mapped["Concept"] = relationship(
        "Concept",
        back_populates="series_families",
        lazy="selectin",
    )
    geography: Mapped["Geography"] = relationship(
        "Geography",
        back_populates="series_families",
        lazy="selectin",
    )
    members: Mapped[list["SeriesFamilyMember"]] = relationship(
        "SeriesFamilyMember",
        back_populates="family",
        lazy="selectin",
        passive_deletes=True,
    )


class SeriesFamilyMember(Base):
    """V3 association row with a composite primary key and timestamps."""

    __tablename__ = "series_family_members"
    __table_args__ = (UniqueConstraint("series_id", name="uq_series_family_members_series_id"),)

    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("series_families.id", ondelete="CASCADE"),
        primary_key=True,
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("series.id", ondelete="CASCADE"),
        primary_key=True,
    )
    variant: Mapped[str | None] = mapped_column(String(), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    family: Mapped["SeriesFamily"] = relationship(
        "SeriesFamily",
        back_populates="members",
        lazy="selectin",
    )
    series: Mapped["Series"] = relationship(
        "Series",
        back_populates="family_member",
        lazy="selectin",
    )


__all__ = ["Series", "SeriesFamily", "SeriesFamilyMember", "SeriesHierarchyEdge"]
