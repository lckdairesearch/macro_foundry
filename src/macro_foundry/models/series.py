"""Series-domain SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, String, UniqueConstraint, func
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
    description: Mapped[str | None] = mapped_column(String(), nullable=True)
    origin_type: Mapped[OriginType] = mapped_column(
        SAEnum(OriginType, native_enum=False, name="ck_series_origin_type", validate_strings=True),
        nullable=False,
    )
    geography_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("geographies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    frequency: Mapped[Frequency] = mapped_column(
        SAEnum(Frequency, native_enum=False, name="ck_series_frequency", validate_strings=True),
        nullable=False,
    )
    temporal_stock_flow: Mapped[TemporalStockFlow] = mapped_column(
        SAEnum(
            TemporalStockFlow,
            native_enum=False,
            name="ck_series_temporal_stock_flow",
            validate_strings=True,
        ),
        nullable=False,
    )
    unit_kind: Mapped[UnitKind] = mapped_column(
        SAEnum(UnitKind, native_enum=False, name="ck_series_unit_kind", validate_strings=True),
        nullable=False,
    )
    unit_scale: Mapped[UnitScale] = mapped_column(
        SAEnum(UnitScale, native_enum=False, name="ck_series_unit_scale", validate_strings=True),
        nullable=False,
    )
    unit_label: Mapped[str | None] = mapped_column(String(), nullable=True)
    price_basis: Mapped[PriceBasis | None] = mapped_column(
        SAEnum(PriceBasis, native_enum=False, name="ck_series_price_basis", validate_strings=True),
        nullable=True,
    )
    currency_code: Mapped[str | None] = mapped_column(String(), nullable=True)
    measure: Mapped[Measure] = mapped_column(
        SAEnum(Measure, native_enum=False, name="ck_series_measure", validate_strings=True),
        nullable=False,
    )
    measure_horizon: Mapped[MeasureHorizon | None] = mapped_column(
        SAEnum(MeasureHorizon, native_enum=False, name="ck_series_measure_horizon", validate_strings=True),
        nullable=True,
    )
    annualized: Mapped[bool] = mapped_column(Boolean, nullable=False)
    seasonal_adjustment: Mapped[SeasonalAdjustment] = mapped_column(
        SAEnum(
            SeasonalAdjustment,
            native_enum=False,
            name="ck_series_seasonal_adjustment",
            validate_strings=True,
        ),
        nullable=False,
    )
    reference_kind: Mapped[ReferenceKind | None] = mapped_column(
        SAEnum(ReferenceKind, native_enum=False, name="ck_series_reference_kind", validate_strings=True),
        nullable=True,
    )
    reference_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_label: Mapped[str | None] = mapped_column(String(), nullable=True)
    replaced_by_series_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("series.id", ondelete="RESTRICT"),
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


class SeriesFamily(TimestampedBase):
    """Series family grouping one concept and one geography."""

    __tablename__ = "series_families"
    __table_args__ = (UniqueConstraint("code", name="uq_series_families_code"),)

    code: Mapped[str] = mapped_column(String(), nullable=False)
    name: Mapped[str] = mapped_column(String(), nullable=False)
    description: Mapped[str | None] = mapped_column(String(), nullable=True)
    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("concepts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    geography_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("geographies.id", ondelete="RESTRICT"),
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


__all__ = ["Series", "SeriesFamily", "SeriesFamilyMember"]
