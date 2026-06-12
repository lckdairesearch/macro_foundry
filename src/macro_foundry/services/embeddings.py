"""Embedding text recipes and client calls for ADR 0020.

Changing label wording, field order, or the humanization maps changes the
embedding input recipe, invalidates stored embeddings, and requires backfill.
"""

from __future__ import annotations

import asyncio
import hashlib

import openai

from macro_foundry.enums import Frequency, Measure, SeasonalAdjustment, UnitKind
from macro_foundry.config import settings
from macro_foundry.models.concept import Concept
from macro_foundry.models.series import Series, SeriesFamily

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
        ]
    )


def compose_family_embedding_input(family: SeriesFamily) -> str:
    concept = family.concept
    geography = family.geography
    return _compose(
        [
            _line("Type", "SeriesFamily"),
            _line("Code", family.code),
            _line("Name", family.name),
            _line("Description", family.description),
            _line("Geography", geography.name if geography is not None else None),
            _line(
                "Concept",
                f"{concept.name} ({concept.code})" if concept is not None else None,
            ),
            _line(
                "Concept description",
                concept.description if concept is not None else None,
            ),
        ]
    )


def compose_series_embedding_input(series: Series) -> str:
    alt_names = ", ".join(series.alt_name) if series.alt_name else None
    family_member = series.family_member
    family = family_member.family if family_member is not None else None
    concept = family.concept if family is not None else None
    geography = series.geography
    return _compose(
        [
            _line("Type", "Series"),
            _line("Code", series.code),
            _line("Name", series.name),
            _line("Alt names", alt_names),
            _line("Description", series.description),
            _line("Geography", geography.name if geography is not None else None),
            _line("Frequency", FREQUENCY_HUMAN.get(series.frequency)),
            _line("Unit", UNIT_KIND_HUMAN.get(series.unit_kind)),
            _line("Unit label", series.unit_label),
            _line("Measure", MEASURE_HUMAN.get(series.measure)),
            _line(
                "Seasonal adjustment",
                SEASONAL_ADJUSTMENT_HUMAN.get(series.seasonal_adjustment),
            ),
            _line("Family", f"{family.name} ({family.code})" if family is not None else None),
            _line(
                "Concept",
                f"{concept.name} ({concept.code})" if concept is not None else None,
            ),
        ]
    )


def hash_embedding_input(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _openai_client_from_settings() -> openai.AsyncOpenAI:
    api_key = settings.llm.openai_api_key
    if api_key is None:
        raise RuntimeError("OPENAI_API_KEY is required for embedding writes.")
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


async def embed_text(text: str) -> list[float]:
    client = _openai_client_from_settings()
    for attempt in range(2):
        try:
            response = await client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text,
            )
            return [float(value) for value in response.data[0].embedding]
        except Exception as exc:
            if not _is_transient_embedding_error(exc) or attempt == 1:
                raise
            await asyncio.sleep(0.5)
    raise AssertionError("unreachable")
