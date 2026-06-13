"""Focused Phase 7 schema validation coverage."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from macro_foundry.enums import (
    Action,
    AuthScheme,
    CodeStandard,
    Frequency,
    GeographyType,
    Measure,
    MeasureHorizon,
    OriginType,
    SeasonalAdjustment,
    TargetType,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.schemas import (
    GeographyCreate,
    GeographyUpdate,
    ObservationCreate,
    ObservationUpdate,
    ProviderCreate,
    SeriesCreate,
    SeriesUpdate,
    TagCreate,
    TagRead,
)


def test_tag_create_requires_code_and_name() -> None:
    payload = TagCreate(code="PRICES", name="Prices")
    assert payload.code == "PRICES"
    assert payload.name == "Prices"

    with pytest.raises(ValidationError):
        TagCreate(name="Prices")


def test_tag_read_exposes_code_as_natural_key() -> None:
    assert "code" in TagRead.model_fields
    assert "name" in TagRead.model_fields


def test_geography_create_requires_parent_for_subnational_types() -> None:
    with pytest.raises(ValidationError):
        GeographyCreate(
            code="US-CA",
            name="California",
            type=GeographyType.SUBNATIONAL,
            code_standard=CodeStandard.ISO_3166_2,
        )


def test_series_create_accepts_valid_growth_series() -> None:
    payload = SeriesCreate(
        code="US_CPI_YOY",
        name="US CPI YoY",
        origin_type=OriginType.INGESTED,
        geography_id=uuid4(),
        frequency=Frequency.MONTHLY,
        temporal_stock_flow=TemporalStockFlow.INDEX,
        unit_kind=UnitKind.PERCENT,
        unit_scale=UnitScale.ONE,
        measure=Measure.GROWTH,
        measure_horizon=MeasureHorizon.YOY,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.NSA,
        is_active=True,
    )

    assert payload.measure_horizon is MeasureHorizon.YOY


def test_series_create_rejects_currency_without_currency_code() -> None:
    with pytest.raises(ValidationError):
        SeriesCreate(
            code="JP_GDP_NOMINAL",
            name="Japan GDP",
            origin_type=OriginType.INGESTED,
            geography_id=uuid4(),
            frequency=Frequency.QUARTERLY,
            temporal_stock_flow=TemporalStockFlow.FLOW,
            unit_kind=UnitKind.CURRENCY,
            unit_scale=UnitScale.BILLION,
            measure=Measure.LEVEL,
            annualized=False,
            seasonal_adjustment=SeasonalAdjustment.SAAR,
            is_active=True,
        )


def test_observation_create_rejects_invalid_period_bounds() -> None:
    with pytest.raises(ValidationError):
        ObservationCreate(
            series_id=uuid4(),
            period_start=date(2026, 1, 31),
            period_end=date(2026, 1, 1),
            vintage_date=date(2026, 2, 15),
        )


def test_series_update_allows_partial_cross_field_patch() -> None:
    payload = SeriesUpdate(measure=Measure.GROWTH)

    assert payload.measure is Measure.GROWTH


def test_geography_update_allows_partial_parent_dependent_patch() -> None:
    payload = GeographyUpdate(type=GeographyType.SUBNATIONAL)

    assert payload.type is GeographyType.SUBNATIONAL


def test_observation_update_allows_single_bound_patch() -> None:
    payload = ObservationUpdate(period_end=date(2026, 1, 31))

    assert payload.period_end == date(2026, 1, 31)


def test_provider_schema_exposes_credential_access_metadata() -> None:
    payload = ProviderCreate(
        name="Example Provider",
        type="official",
        auth_scheme=AuthScheme.BEARER_HEADER,
        rate_limit_config={"requests_per_minute": 60, "tier_label": "free"},
        credentials_ref="EXAMPLE_API_KEY",
        is_active=True,
    )

    assert payload.auth_scheme is AuthScheme.BEARER_HEADER
    assert payload.rate_limit_config == {"requests_per_minute": 60, "tier_label": "free"}
    assert Action.SUGGEST_CREDENTIAL_PROVISIONING.value == "suggest_credential_provisioning"
    assert TargetType.CREDENTIAL_REF.value == "credential_ref"
