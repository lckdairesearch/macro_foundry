"""Minimum sanity check for ADR 0020 embeddings.

Print-only. No DB writes, no schema changes, no migration required.
Verifies the pipeline end-to-end:
  1. Fetch every concept / series_family / series from test_db.
  2. Compose a text input per row using the locked recipe.
  3. Call OpenAI `text-embedding-3-small` once for the whole batch.
  4. Run probe queries through cosine similarity and rank.

Run: `uv run python scripts/embeddings_sanity.py`
"""

from __future__ import annotations

import asyncio
import math

from openai import AsyncOpenAI
from sqlalchemy import select

from macro_foundry.config import settings
from macro_foundry.db.session import create_async_engine_for_url, create_session_factory
from macro_foundry.enums import Frequency, Measure, SeasonalAdjustment, UnitKind
from macro_foundry.models.concept import Concept
from macro_foundry.models.series import Series, SeriesFamily

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

PROBE_QUERIES = [
    "headline inflation rate, monthly, United States",
    "real GDP growth, quarterly, US",
    "core CPI excluding food and energy",
    "nominal output of the US economy",
]

# --- Humanization maps ------------------------------------------------------
# Changes to any of these maps count as recipe changes — they become part
# of the composed text and any change invalidates existing embeddings.

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


# --- Recipe -----------------------------------------------------------------
# Empty / None fields omit the entire line. Order is fixed.

def _line(label: str, value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return f"{label}: {text}"


def _compose(lines: list[str | None]) -> str:
    return "\n".join(line for line in lines if line is not None)


def compose_concept(c: Concept) -> str:
    return _compose([
        _line("Type", "Concept"),
        _line("Code", c.code),
        _line("Name", c.name),
        _line("Description", c.description),
    ])


def compose_family(f: SeriesFamily) -> str:
    return _compose([
        _line("Type", "SeriesFamily"),
        _line("Code", f.code),
        _line("Name", f.name),
        _line("Description", f.description),
        _line("Geography", f.geography.name if f.geography else None),
        _line("Concept", f"{f.concept.name} ({f.concept.code})" if f.concept else None),
        _line("Concept description", f.concept.description if f.concept else None),
    ])


def compose_series(s: Series) -> str:
    alt = ", ".join(s.alt_name) if s.alt_name else None
    family = s.family_member.family if s.family_member else None
    concept = family.concept if family else None
    return _compose([
        _line("Type", "Series"),
        _line("Code", s.code),
        _line("Name", s.name),
        _line("Alt names", alt),
        _line("Description", s.description),
        _line("Geography", s.geography.name if s.geography else None),
        _line("Frequency", FREQUENCY_HUMAN.get(s.frequency)),
        _line("Unit", UNIT_KIND_HUMAN.get(s.unit_kind)),
        _line("Unit label", s.unit_label),
        _line("Measure", MEASURE_HUMAN.get(s.measure)),
        _line("Seasonal adjustment", SEASONAL_ADJUSTMENT_HUMAN.get(s.seasonal_adjustment)),
        _line("Family", f"{family.name} ({family.code})" if family else None),
        _line("Concept", f"{concept.name} ({concept.code})" if concept else None),
    ])


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb)


async def main() -> None:
    api_key = settings.llm.openai_api_key
    if api_key is None:
        raise SystemExit("OPENAI_API_KEY missing — set it in .env.local")
    client = AsyncOpenAI(api_key=api_key.get_secret_value())

    engine = create_async_engine_for_url(settings.db.test_url)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        concepts = list((await session.execute(select(Concept))).scalars().all())
        families = list((await session.execute(select(SeriesFamily))).scalars().all())
        series = list((await session.execute(select(Series))).scalars().all())

    items: list[tuple[str, str, str]] = []
    for c in concepts:
        items.append(("concept", c.code, compose_concept(c)))
    for f in families:
        items.append(("family", f.code, compose_family(f)))
    for s in series:
        items.append(("series", s.code, compose_series(s)))

    print(
        f"Composed {len(items)} inputs "
        f"({len(concepts)} concepts, {len(families)} families, {len(series)} series)"
    )
    if not items:
        await engine.dispose()
        return

    print("\n--- Sample composed inputs ---")
    for kind, code, text in items:
        if kind == "series" and "CPI_HEADLINE" in code:
            print(f"[{kind}: {code}]")
            print(text)
            print()
            break
    print("------------------------------\n")

    resp = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[t for (_, _, t) in items],
    )

    print(f"OpenAI returned {len(resp.data)} embeddings")
    print(f"  model: {resp.model}")
    print(f"  usage: {resp.usage}")
    print(f"  dim:   {len(resp.data[0].embedding)} (expected {EMBEDDING_DIMENSIONS})")

    row_vectors = [emb.embedding for emb in resp.data]

    print("\n=== Probe queries (cosine similarity, top 5) ===")
    probe_resp = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=PROBE_QUERIES,
    )
    for query, query_emb in zip(PROBE_QUERIES, probe_resp.data, strict=True):
        qv = query_emb.embedding
        scored = [
            (cosine(qv, rv), kind, code)
            for (kind, code, _), rv in zip(items, row_vectors, strict=True)
        ]
        scored.sort(reverse=True)
        print(f"\nQuery: {query!r}")
        for sim, kind, code in scored[:5]:
            print(f"  {sim:+.4f}  {kind:7s} {code}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
