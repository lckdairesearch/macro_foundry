"""Read-only macrodb MCP tool implementations.

The concept/indicator drill-down and search tools were retired with the V7
conceptual spine (ADR 0025); category-aware navigation will be reintroduced once
the `categories` tree lands. What remains is provider/series-grounded: canonical
series semantic search, the selector registry surface, and enum introspection.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.ingestion.runtime.selectors import get_selector, list_selector_types
from macro_foundry.models import Series
from macro_foundry.schemas import SeriesRead, SeriesSearchHit
from macro_foundry.schemas._base import SchemaModel
from macro_foundry.services.embeddings import embed_text


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
    "ListEnumValuesArgs",
    "MacrodbReadTools",
    "SelectorConfigValidationArgs",
    "SelectorSchemaArgs",
    "SelectorValidationRead",
]
