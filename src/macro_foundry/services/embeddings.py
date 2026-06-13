"""Embedding recipe helpers for semantic catalog search.

Changing the label wording, field order, or humanization maps changes the
composed input text and therefore invalidates existing embeddings. When the
recipe changes, existing rows become stale and must be repaired with
`macrodb embeddings backfill`.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence

import openai

from macro_foundry.config import settings
from macro_foundry.enums import Frequency, Measure, SeasonalAdjustment, UnitKind
from macro_foundry.models import Concept, Indicator, Series

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

FREQUENCY_HUMAN: dict[Frequency, str] = {
    Frequency.DAILY: "daily",
    Frequency.WEEKLY: "weekly",
    Frequency.MONTHLY: "monthly",
    Frequency.QUARTERLY: "quarterly",
    Frequency.SEMI_ANNUAL: "semi-annual",
    Frequency.ANNUAL: "annual",
}

UNIT_KIND_HUMAN: dict[UnitKind, str] = {
    UnitKind.INDEX: "index",
    UnitKind.PERCENT: "percent",
    UnitKind.BPS: "basis points",
    UnitKind.CURRENCY: "currency",
    UnitKind.COUNT: "count",
    UnitKind.QUANTITY: "quantity",
    UnitKind.RATIO: "ratio",
    UnitKind.NONE: "unitless",
}

MEASURE_HUMAN: dict[Measure, str] = {
    Measure.LEVEL: "level",
    Measure.GROWTH: "growth",
    Measure.CHANGE: "change",
}

SEASONAL_ADJUSTMENT_HUMAN: dict[SeasonalAdjustment, str] = {
    SeasonalAdjustment.SA: "seasonally adjusted",
    SeasonalAdjustment.SAAR: "seasonally adjusted annual rate",
    SeasonalAdjustment.NSA: "not seasonally adjusted",
    SeasonalAdjustment.UNKNOWN: "unknown",
}


def _line(label: str, value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return f"{label}: {text}"


def _compose(lines: list[str | None]) -> str:
    return "\n".join(line for line in lines if line is not None)


def compose_concept_embedding_input(concept: Concept) -> str:
    return _compose(
        [
            _line("Type", "Concept"),
            _line("Code", concept.code),
            _line("Name", concept.name),
            _line("Description", concept.description),
        ],
    )


def compose_indicator_embedding_input(indicator: Indicator) -> str:
    # NOTE: the "Type" label below is "Indicator" to match the renamed schema
    # (ADR 0021). This string is part of the text fed to the embedding model, so
    # this value drifts every stored embedding_input_hash on `indicators` and
    # requires an indicators-only re-embed (`macrodb embeddings backfill`). This
    # is the sanctioned `compose_indicator` label change in ADR 0020's
    # recipe-change scope table.
    return _compose(
        [
            _line("Type", "Indicator"),
            _line("Code", indicator.code),
            _line("Name", indicator.name),
            _line("Description", indicator.description),
            _line("Geography", indicator.geography.name if indicator.geography else None),
            _line(
                "Concept",
                f"{indicator.concept.name} ({indicator.concept.code})" if indicator.concept else None,
            ),
            _line("Concept description", indicator.concept.description if indicator.concept else None),
        ],
    )


def compose_series_embedding_input(series: Series) -> str:
    alt_names = ", ".join(series.alt_name) if series.alt_name else None
    indicator = series.indicator_variant.indicator if series.indicator_variant else None
    concept = indicator.concept if indicator else None
    return _compose(
        [
            _line("Type", "Series"),
            _line("Code", series.code),
            _line("Name", series.name),
            _line("Alt names", alt_names),
            _line("Description", series.description),
            _line("Geography", series.geography.name if series.geography else None),
            _line("Frequency", FREQUENCY_HUMAN.get(series.frequency)),
            _line("Unit", UNIT_KIND_HUMAN.get(series.unit_kind)),
            _line("Unit label", series.unit_label),
            _line("Measure", MEASURE_HUMAN.get(series.measure)),
            _line("Seasonal adjustment", SEASONAL_ADJUSTMENT_HUMAN.get(series.seasonal_adjustment)),
            _line("Indicator", f"{indicator.name} ({indicator.code})" if indicator else None),
            _line("Concept", f"{concept.name} ({concept.code})" if concept else None),
        ],
    )


def hash_embedding_input(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _client() -> openai.AsyncOpenAI:
    api_key = settings.llm.openai_api_key
    if api_key is None:
        raise ValueError("OPENAI_API_KEY is required for embeddings")
    return openai.AsyncOpenAI(api_key=api_key.get_secret_value())


def _is_quota_error(exc: openai.RateLimitError) -> bool:
    body = exc.body
    if not isinstance(body, dict):
        return False
    error = body.get("error")
    if not isinstance(error, dict):
        return False
    return error.get("code") == "insufficient_quota"


def _is_transient_embedding_error(exc: Exception) -> bool:
    if isinstance(exc, openai.RateLimitError):
        return not _is_quota_error(exc)
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError)):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code >= 500
    return isinstance(exc, asyncio.TimeoutError)


async def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    if not texts:
        return []
    client = _client()
    for attempt in range(2):
        try:
            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=list(texts),
            )
            return [list(item.embedding) for item in response.data]
        except Exception as exc:
            if not _is_transient_embedding_error(exc) or attempt == 1:
                raise
            await asyncio.sleep(0.5)
    raise AssertionError("unreachable")


async def embed_text(text: str) -> list[float]:
    vectors = await embed_texts([text])
    return vectors[0]
