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
    SeriesFamily,
    SeriesFamilyMember,
    SeriesSource,
)
from macro_foundry.schemas import ConceptRead, SeriesFamilyReadDetail, SeriesRead
from macro_foundry.schemas._base import SchemaModel


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

    async def lookup_family(
        self, args: LookupFamilyArgs
    ) -> SeriesFamilyReadDetail | None:
        """Return the series family with its member rows, or None."""

        family = await self._session.scalar(
            select(SeriesFamily)
            .where(SeriesFamily.code == args.code)
            .options(selectinload(SeriesFamily.members)),
        )
        if family is None:
            return None
        return SeriesFamilyReadDetail.model_validate(family)

    async def find_sibling_series(
        self, args: FindSiblingSeriesArgs
    ) -> list[SeriesRead]:
        """Return series rows attached to a family."""

        result = await self._session.execute(
            select(Series)
            .join(SeriesFamilyMember, SeriesFamilyMember.series_id == Series.id)
            .where(SeriesFamilyMember.family_id == args.family_id)
            .order_by(SeriesFamilyMember.is_primary.desc(), Series.code),
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
            .join(SeriesFamilyMember, SeriesFamilyMember.series_id == Series.id)
            .join(SeriesFamily, SeriesFamily.id == SeriesFamilyMember.family_id)
            .join(SeriesSource, SeriesSource.series_id == Series.id)
            .join(
                ProviderCatalog, ProviderCatalog.id == SeriesSource.provider_catalog_id
            )
            .where(
                SeriesFamily.concept_id == args.concept_id,
                ProviderCatalog.provider_id == args.provider_id,
            )
            .order_by(Series.code),
        )
        return [SeriesRead.model_validate(series) for series in result.scalars().all()]

    async def list_series_for_concept(
        self, args: ListSeriesForConceptArgs
    ) -> list[SeriesRead]:
        """Return series belonging to any family for a concept."""

        result = await self._session.execute(
            select(Series)
            .join(SeriesFamilyMember, SeriesFamilyMember.series_id == Series.id)
            .join(SeriesFamily, SeriesFamily.id == SeriesFamilyMember.family_id)
            .where(SeriesFamily.concept_id == args.concept_id)
            .order_by(Series.code),
        )
        return [SeriesRead.model_validate(series) for series in result.scalars().all()]


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
