"""Read-only macrodb MCP tool implementations."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from macro_foundry.ingestion.runtime.selectors import get_selector, list_selector_types
from macro_foundry.models import (
    Concept,
    ProviderCatalog,
    Series,
    Indicator,
    IndicatorVariant,
    SeriesSource,
)
from macro_foundry.schemas import (
    ConceptRead,
    ConceptSearchHit,
    IndicatorSearchHit,
    IndicatorReadDetail,
    SeriesRead,
    SeriesSearchHit,
)
from macro_foundry.schemas._base import SchemaModel
from macro_foundry.services.embeddings import embed_text


class LookupConceptArgs(SchemaModel):
    """Arguments for lookup_concept."""

    code: str


class LookupFamilyArgs(SchemaModel):
    """Arguments for lookup_family."""

    code: str


class FindSiblingSeriesArgs(SchemaModel):
    """Arguments for find_sibling_series."""

    family_id: UUID


class ListSeriesForConceptArgs(SchemaModel):
    """Arguments for list_series_for_concept."""

    concept_id: UUID


class ListProviderSeriesForConceptArgs(SchemaModel):
    """Arguments for list_provider_series_for_concept."""

    provider_id: UUID
    concept_id: UUID


class ListEnumValuesArgs(SchemaModel):
    """Arguments for list_enum_values."""

    table: str
    column: str


class EnumValuesRead(SchemaModel):
    """Read result for list_enum_values."""

    table: str
    column: str
    constraint_name: str
    values: list[str]


class SelectorSchemaArgs(SchemaModel):
    """Arguments for get_selector_schema."""

    selector_type: str


class SelectorConfigValidationArgs(SchemaModel):
    """Arguments for validate_selector_config."""

    selector_type: str
    config: dict[str, Any]
    sample_payload: Any | None = None


class SelectorValidationRead(SchemaModel):
    """Read result for validate_selector_config."""

    is_valid: bool
    errors: tuple[str, ...] = ()


class MacrodbReadTools:
    """Read-only semantic tool surface for macrodb."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lookup_concept(self, args: LookupConceptArgs) -> ConceptRead | None:
        """Return the concept with the requested code, or None."""

        concept = await self._session.scalar(
            select(Concept).where(Concept.code == args.code),
        )
        if concept is None:
            return None
        return ConceptRead.model_validate(concept)

    async def search_concepts(
        self,
        query: str,
        limit: int = 10,
    ) -> list[ConceptSearchHit]:
        """Return ranked semantic-search hits for concept rows."""

        query_vector = await embed_text(query)
        ranking_rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, 1 - (embedding <=> CAST(:query_vec AS vector)) AS similarity
                    FROM concepts
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:query_vec AS vector)
                    LIMIT :limit
                    """,
                ),
                {
                    "query_vec": _vector_literal(query_vector),
                    "limit": limit,
                },
            )
        ).mappings().all()
        if not ranking_rows:
            return []

        ranked_ids = [row["id"] for row in ranking_rows]
        concept_rows = (
            await self._session.execute(
                select(Concept).where(Concept.id.in_(ranked_ids)),
            )
        ).scalars().all()
        concepts_by_id = {concept.id: concept for concept in concept_rows}
        return [
            ConceptSearchHit(
                concept=ConceptRead.model_validate(concepts_by_id[row["id"]]),
                similarity=_clamp_similarity(float(row["similarity"])),
            )
            for row in ranking_rows
        ]

    async def lookup_family(
        self, args: LookupFamilyArgs
    ) -> IndicatorReadDetail | None:
        """Return the indicator with its variant rows, or None."""

        indicator = await self._session.scalar(
            select(Indicator)
            .where(Indicator.code == args.code)
            .options(selectinload(Indicator.variants)),
        )
        if indicator is None:
            return None
        return IndicatorReadDetail.model_validate(indicator)

    async def find_sibling_series(
        self, args: FindSiblingSeriesArgs
    ) -> list[SeriesRead]:
        """Return series rows attached to an indicator."""

        result = await self._session.execute(
            select(Series)
            .join(IndicatorVariant, IndicatorVariant.series_id == Series.id)
            .where(IndicatorVariant.indicator_id == args.family_id)
            .order_by(IndicatorVariant.is_default.desc(), Series.code),
        )
        return [SeriesRead.model_validate(series) for series in result.scalars().all()]

    async def list_selector_types(self) -> list[str]:
        """Return registered selector_type names."""

        return list_selector_types()

    async def get_selector_schema(self, args: SelectorSchemaArgs) -> dict[str, Any]:
        """Return a selector's JSON config schema."""

        return get_selector(args.selector_type).config_schema

    async def validate_selector_config(
        self,
        args: SelectorConfigValidationArgs,
    ) -> SelectorValidationRead:
        """Validate selector config with an optional sample payload probe."""

        selector = get_selector(args.selector_type)
        validation = selector.validate(args.config)
        if validation.is_valid and args.sample_payload is not None:
            try:
                selector.extract(args.sample_payload, args.config)
            except ValueError as exc:
                return SelectorValidationRead(is_valid=False, errors=(str(exc),))
        return SelectorValidationRead(
            is_valid=validation.is_valid,
            errors=validation.errors,
        )

    async def list_enum_values(self, args: ListEnumValuesArgs) -> EnumValuesRead:
        """Return enum values parsed from the column's named CHECK constraint."""

        constraint_name = f"ck_{args.table}_{args.column}"
        constraint_definition = await self._session.scalar(
            text(
                """
                SELECT pg_get_constraintdef(c.oid)
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public'
                  AND t.relname = :table_name
                  AND c.conname = :constraint_name
                """,
            ),
            {
                "table_name": args.table,
                "constraint_name": constraint_name,
            },
        )
        if constraint_definition is None:
            raise ValueError(f"Constraint {constraint_name!r} was not found")
        return EnumValuesRead(
            table=args.table,
            column=args.column,
            constraint_name=constraint_name,
            values=_parse_check_constraint_values(str(constraint_definition)),
        )

    async def list_provider_series_for_concept(
        self,
        args: ListProviderSeriesForConceptArgs,
    ) -> list[SeriesRead]:
        """Return provider-linked series for a concept."""

        result = await self._session.execute(
            select(Series)
            .join(IndicatorVariant, IndicatorVariant.series_id == Series.id)
            .join(Indicator, Indicator.id == IndicatorVariant.indicator_id)
            .join(SeriesSource, SeriesSource.series_id == Series.id)
            .join(
                ProviderCatalog, ProviderCatalog.id == SeriesSource.provider_catalog_id
            )
            .where(
                Indicator.concept_id == args.concept_id,
                ProviderCatalog.provider_id == args.provider_id,
            )
            .order_by(Series.code),
        )
        return [SeriesRead.model_validate(series) for series in result.scalars().all()]

    async def list_series_for_concept(
        self, args: ListSeriesForConceptArgs
    ) -> list[SeriesRead]:
        """Return series belonging to any indicator for a concept."""

        result = await self._session.execute(
            select(Series)
            .join(IndicatorVariant, IndicatorVariant.series_id == Series.id)
            .join(Indicator, Indicator.id == IndicatorVariant.indicator_id)
            .where(Indicator.concept_id == args.concept_id)
            .order_by(Series.code),
        )
        return [SeriesRead.model_validate(series) for series in result.scalars().all()]

    async def search_series(
        self,
        query: str,
        limit: int = 10,
    ) -> list[SeriesSearchHit]:
        """Return ranked semantic-search hits for canonical series rows."""

        query_vector = await embed_text(query)
        ranking_rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, 1 - (embedding <=> CAST(:query_vec AS vector)) AS similarity
                    FROM series
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:query_vec AS vector)
                    LIMIT :limit
                    """,
                ),
                {
                    "query_vec": _vector_literal(query_vector),
                    "limit": limit,
                },
            )
        ).mappings().all()
        if not ranking_rows:
            return []

        ranked_ids = [row["id"] for row in ranking_rows]
        series_rows = (
            await self._session.execute(
                select(Series).where(Series.id.in_(ranked_ids)),
            )
        ).scalars().all()
        series_by_id = {series.id: series for series in series_rows}
        return [
            SeriesSearchHit(
                series=SeriesRead.model_validate(series_by_id[row["id"]]),
                similarity=_clamp_similarity(float(row["similarity"])),
            )
            for row in ranking_rows
        ]

    async def search_series_families(
        self,
        query: str,
        limit: int = 10,
    ) -> list[IndicatorSearchHit]:
        """Return ranked semantic-search hits for indicator rows."""

        query_vector = await embed_text(query)
        ranking_rows = (
            await self._session.execute(
                text(
                    """
                    SELECT id, 1 - (embedding <=> CAST(:query_vec AS vector)) AS similarity
                    FROM indicators
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:query_vec AS vector)
                    LIMIT :limit
                    """,
                ),
                {
                    "query_vec": _vector_literal(query_vector),
                    "limit": limit,
                },
            )
        ).mappings().all()
        if not ranking_rows:
            return []

        ranked_ids = [row["id"] for row in ranking_rows]
        indicator_rows = (
            await self._session.execute(
                select(Indicator)
                .where(Indicator.id.in_(ranked_ids))
                .options(selectinload(Indicator.variants)),
            )
        ).scalars().all()
        indicators_by_id = {indicator.id: indicator for indicator in indicator_rows}
        return [
            IndicatorSearchHit(
                indicator=IndicatorReadDetail.model_validate(indicators_by_id[row["id"]]),
                similarity=_clamp_similarity(float(row["similarity"])),
            )
            for row in ranking_rows
        ]


def _parse_check_constraint_values(constraint_definition: str) -> list[str]:
    values = [
        match.group("value").replace("''", "'")
        for match in re.finditer(
            r"'(?P<value>(?:''|[^'])*)'(?=::)", constraint_definition
        )
    ]
    if not values:
        raise ValueError(
            f"No enum values found in constraint definition {constraint_definition!r}"
        )
    return values


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def _clamp_similarity(value: float) -> float:
    return max(0.0, min(1.0, value))


__all__ = [
    "EnumValuesRead",
    "FindSiblingSeriesArgs",
    "ListEnumValuesArgs",
    "ListProviderSeriesForConceptArgs",
    "ListSeriesForConceptArgs",
    "LookupConceptArgs",
    "LookupFamilyArgs",
    "MacrodbReadTools",
    "SelectorConfigValidationArgs",
    "SelectorSchemaArgs",
    "SelectorValidationRead",
]
