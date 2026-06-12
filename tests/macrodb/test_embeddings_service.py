"""Tests for the embedding service module (issue 61)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import openai as openai_lib
import pytest
from pydantic import SecretStr

from macro_foundry.enums.geography import CodeStandard, GeographyType
from macro_foundry.enums.series import (
    Frequency,
    Measure,
    OriginType,
    SeasonalAdjustment,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
)
from macro_foundry.models.concept import Concept
from macro_foundry.models.geography import Geography
from macro_foundry.models.series import Indicator, IndicatorVariant, Series
from macro_foundry.services.embeddings import FREQUENCY_HUMAN
from macro_foundry.services.embeddings import MEASURE_HUMAN
from macro_foundry.services.embeddings import SEASONAL_ADJUSTMENT_HUMAN
from macro_foundry.services.embeddings import UNIT_KIND_HUMAN
from macro_foundry.services.embeddings import compose_concept_embedding_input
from macro_foundry.services.embeddings import compose_indicator_embedding_input
from macro_foundry.services.embeddings import compose_series_embedding_input
from macro_foundry.services.embeddings import embed_text
from macro_foundry.services.embeddings import hash_embedding_input


@pytest.mark.no_db
def test_compose_concept_embedding_input_uses_locked_recipe_labels() -> None:
    concept = Concept(
        code="CPI",
        name="Consumer Price Index",
        description="Measures consumer price inflation.",
    )

    assert compose_concept_embedding_input(concept) == (
        "Type: Concept\n"
        "Code: CPI\n"
        "Name: Consumer Price Index\n"
        "Description: Measures consumer price inflation."
    )


@pytest.mark.no_db
def test_compose_indicator_embedding_input_includes_parent_context() -> None:
    concept = Concept(
        code="CPI",
        name="Consumer Price Index",
        description="Measures consumer price inflation.",
    )
    geography = Geography(
        code="USA",
        name="United States",
        type=GeographyType.COUNTRY,
        code_standard=CodeStandard.ISO_3166_1,
    )
    family = Indicator(
        code="USA_CPI",
        name="USA CPI",
        description="Consumer price index family for the United States.",
        concept=concept,
        geography=geography,
    )

    assert compose_indicator_embedding_input(family) == (
        "Type: SeriesFamily\n"
        "Code: USA_CPI\n"
        "Name: USA CPI\n"
        "Description: Consumer price index family for the United States.\n"
        "Geography: United States\n"
        "Concept: Consumer Price Index (CPI)\n"
        "Concept description: Measures consumer price inflation."
    )


@pytest.mark.no_db
def test_compose_series_embedding_input_humanizes_enums_and_includes_parents() -> None:
    concept = Concept(
        code="CPI",
        name="Consumer Price Index",
        description="Measures consumer price inflation.",
    )
    geography = Geography(
        code="USA",
        name="United States",
        type=GeographyType.COUNTRY,
        code_standard=CodeStandard.ISO_3166_1,
    )
    family = Indicator(
        code="USA_CPI",
        name="USA CPI",
        description="Consumer price index family for the United States.",
        concept=concept,
        geography=geography,
    )
    series = Series(
        code="USA_CPI_HEADLINE_M_NSA",
        name="USA Headline CPI",
        description="Headline consumer price index for the United States.",
        origin_type=OriginType.INGESTED,
        geography=geography,
        frequency=Frequency.MONTHLY,
        temporal_stock_flow=TemporalStockFlow.INDEX,
        unit_kind=UnitKind.INDEX,
        unit_scale=UnitScale.ONE,
        unit_label="index",
        measure=Measure.LEVEL,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.NSA,
        is_active=True,
    )
    series.alt_name = ["Headline CPI", "CPI-U All Items"]
    IndicatorVariant(
        indicator=family,
        series=series,
        label="Headline",
        is_default=True,
    )

    assert compose_series_embedding_input(series) == (
        "Type: Series\n"
        "Code: USA_CPI_HEADLINE_M_NSA\n"
        "Name: USA Headline CPI\n"
        "Alt names: Headline CPI, CPI-U All Items\n"
        "Description: Headline consumer price index for the United States.\n"
        "Geography: United States\n"
        "Frequency: monthly\n"
        "Unit: index\n"
        "Unit label: index\n"
        "Measure: level\n"
        "Seasonal adjustment: not seasonally adjusted\n"
        "Family: USA CPI (USA_CPI)\n"
        "Concept: Consumer Price Index (CPI)"
    )


@pytest.mark.no_db
def test_hash_embedding_input_is_deterministic_and_truncated() -> None:
    text = "Type: Concept\nCode: CPI\nName: Consumer Price Index"

    assert hash_embedding_input(text) == hash_embedding_input(text)
    assert len(hash_embedding_input(text)) == 16


@pytest.mark.no_db
def test_compose_series_embedding_input_omits_empty_lines() -> None:
    geography = Geography(
        code="USA",
        name="United States",
        type=GeographyType.COUNTRY,
        code_standard=CodeStandard.ISO_3166_1,
    )
    series = Series(
        code="USA_GDP_Q",
        name="USA GDP",
        description="",
        origin_type=OriginType.INGESTED,
        geography=geography,
        frequency=Frequency.QUARTERLY,
        temporal_stock_flow=TemporalStockFlow.FLOW,
        unit_kind=UnitKind.CURRENCY,
        unit_scale=UnitScale.BILLION,
        unit_label="",
        currency_code="USD",
        measure=Measure.LEVEL,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.SAAR,
        is_active=True,
    )
    series.alt_name = []

    assert compose_series_embedding_input(series) == (
        "Type: Series\n"
        "Code: USA_GDP_Q\n"
        "Name: USA GDP\n"
        "Geography: United States\n"
        "Frequency: quarterly\n"
        "Unit: currency\n"
        "Measure: level\n"
        "Seasonal adjustment: seasonally adjusted annual rate"
    )


@pytest.mark.no_db
def test_humanization_maps_match_adr_0020_addendum() -> None:
    assert FREQUENCY_HUMAN == {
        Frequency.DAILY: "daily",
        Frequency.WEEKLY: "weekly",
        Frequency.MONTHLY: "monthly",
        Frequency.QUARTERLY: "quarterly",
        Frequency.SEMI_ANNUAL: "semi-annual",
        Frequency.ANNUAL: "annual",
    }
    assert UNIT_KIND_HUMAN == {
        UnitKind.INDEX: "index",
        UnitKind.PERCENT: "percent",
        UnitKind.BPS: "basis points",
        UnitKind.CURRENCY: "currency",
        UnitKind.COUNT: "count",
        UnitKind.QUANTITY: "quantity",
        UnitKind.RATIO: "ratio",
        UnitKind.NONE: "unitless",
    }
    assert MEASURE_HUMAN == {
        Measure.LEVEL: "level",
        Measure.GROWTH: "growth",
        Measure.CHANGE: "change",
    }
    assert SEASONAL_ADJUSTMENT_HUMAN == {
        SeasonalAdjustment.SA: "seasonally adjusted",
        SeasonalAdjustment.SAAR: "seasonally adjusted annual rate",
        SeasonalAdjustment.NSA: "not seasonally adjusted",
        SeasonalAdjustment.UNKNOWN: "unknown",
    }


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_embed_text_uses_settings_key_and_returns_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macro_foundry.services import embeddings

    captured: dict[str, str | None] = {}

    async def _create(*, model: str, input: list[str]) -> SimpleNamespace:
        assert model == embeddings.EMBEDDING_MODEL
        assert input == ["hello world"]
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])],
        )

    def _fake_async_openai(*, api_key: str | None = None) -> MagicMock:
        captured["api_key"] = api_key
        client = MagicMock()
        client.embeddings.create = _create
        return client

    monkeypatch.setattr(
        embeddings,
        "settings",
        SimpleNamespace(
            llm=SimpleNamespace(openai_api_key=SecretStr("settings-key")),
        ),
    )
    monkeypatch.setattr(embeddings.openai, "AsyncOpenAI", _fake_async_openai)

    assert await embed_text("hello world") == [0.1, 0.2, 0.3]
    assert captured["api_key"] == "settings-key"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_embed_text_retries_once_on_transient_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macro_foundry.services import embeddings

    calls = 0
    sleeps: list[float] = []
    response = httpx.Response(
        status_code=429,
        request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"),
    )

    async def _create(*, model: str, input: str) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise openai_lib.RateLimitError("rate limited", response=response, body=None)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.9, 0.8])])

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(
        embeddings,
        "settings",
        SimpleNamespace(
            llm=SimpleNamespace(openai_api_key=SecretStr("settings-key")),
        ),
    )
    monkeypatch.setattr(embeddings.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(
        embeddings.openai,
        "AsyncOpenAI",
        lambda *, api_key=None: SimpleNamespace(
            embeddings=SimpleNamespace(create=_create),
        ),
    )

    assert await embeddings.embed_text("hello world") == [0.9, 0.8]
    assert calls == 2
    assert sleeps == [0.5]


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_embed_text_does_not_retry_authentication_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macro_foundry.services import embeddings

    calls = 0
    response = httpx.Response(
        status_code=401,
        request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"),
    )

    async def _create(*, model: str, input: str) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        raise openai_lib.AuthenticationError("bad key", response=response, body=None)

    monkeypatch.setattr(
        embeddings,
        "settings",
        SimpleNamespace(
            llm=SimpleNamespace(openai_api_key=SecretStr("settings-key")),
        ),
    )
    monkeypatch.setattr(
        embeddings.openai,
        "AsyncOpenAI",
        lambda *, api_key=None: SimpleNamespace(
            embeddings=SimpleNamespace(create=_create),
        ),
    )

    with pytest.raises(openai_lib.AuthenticationError, match="bad key"):
        await embeddings.embed_text("hello world")

    assert calls == 1


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_embed_text_does_not_retry_quota_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from macro_foundry.services import embeddings

    calls = 0
    response = httpx.Response(
        status_code=429,
        request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"),
    )

    async def _create(*, model: str, input: str) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        raise openai_lib.RateLimitError(
            "quota exhausted",
            response=response,
            body={"error": {"code": "insufficient_quota"}},
        )

    monkeypatch.setattr(
        embeddings,
        "settings",
        SimpleNamespace(
            llm=SimpleNamespace(openai_api_key=SecretStr("settings-key")),
        ),
    )
    monkeypatch.setattr(
        embeddings.openai,
        "AsyncOpenAI",
        lambda *, api_key=None: SimpleNamespace(
            embeddings=SimpleNamespace(create=_create),
        ),
    )

    with pytest.raises(openai_lib.RateLimitError, match="quota exhausted"):
        await embeddings.embed_text("hello world")

    assert calls == 1
