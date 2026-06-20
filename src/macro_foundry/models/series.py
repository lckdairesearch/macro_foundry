"""Series-domain SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, Boolean, CheckConstraint, Date, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import TimestampedBase
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
from macro_foundry.models._vector import Vector

_EMBEDDING_DIMENSIONS = 1536

if TYPE_CHECKING:
    from macro_foundry.models.category import Category
    from macro_foundry.models.derived import DerivationInput, DerivedSeries
    from macro_foundry.models.geography import Geography
    from macro_foundry.models.observation import Observation
    from macro_foundry.models.provider import SeriesSource


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
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_EMBEDDING_DIMENSIONS), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(), nullable=True)
    embedding_input_hash: Mapped[str | None] = mapped_column(String(), nullable=True)
    origin_type: Mapped[OriginType] = enum_column(
        "series",
        "origin_type",
        OriginType,
        nullable=False,
    )
    # Nullable: draft/unclassified series allowed. Concept-only rule (never a
    # topic node) is enforced app-side (ADR 0025 §3), not by the DB.
    category_id: Mapped[uuid.UUID | None] = fk_uuid(
        "categories.id",
        ondelete="RESTRICT",
        nullable=True,
    )
    # Default reading within (category_id, geography_id); former
    # indicator_variants.is_default. Defaults false at the DB so ORM inserts that
    # omit it are valid. No partial-unique enforced.
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
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
    category: Mapped["Category | None"] = relationship(
        "Category",
        foreign_keys=lambda: [Series.category_id],
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


__all__ = ["Series", "SeriesHierarchyEdge"]
