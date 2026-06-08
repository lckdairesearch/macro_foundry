"""Seed orchestrator."""

from __future__ import annotations

from enum import Enum

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.config import logger
from macro_foundry.models import Geography, GeographyMembership, Provider, ProviderCatalog, Tag
from macro_foundry.seed._shared import SeedOutcome
from macro_foundry.seed.runners import (
    seed_geographies,
    seed_geography_memberships,
    seed_provider_catalogs,
    seed_providers,
    seed_tags,
)


class SeedTarget(str, Enum):
    """Supported seed target names for CLI selection."""

    GEOGRAPHIES = "geographies"
    GEOGRAPHY_MEMBERSHIPS = "geography_memberships"
    TAGS = "tags"
    PROVIDERS = "providers"
    PROVIDER_CATALOGS = "provider_catalogs"


SEED_ORDER: tuple[SeedTarget, ...] = (
    SeedTarget.GEOGRAPHIES,
    SeedTarget.GEOGRAPHY_MEMBERSHIPS,
    SeedTarget.TAGS,
    SeedTarget.PROVIDERS,
    SeedTarget.PROVIDER_CATALOGS,
)

RESET_ORDER: tuple[SeedTarget, ...] = (
    SeedTarget.PROVIDER_CATALOGS,
    SeedTarget.PROVIDERS,
    SeedTarget.TAGS,
    SeedTarget.GEOGRAPHY_MEMBERSHIPS,
    SeedTarget.GEOGRAPHIES,
)


def parse_seed_targets(raw_targets: list[str] | None) -> set[SeedTarget] | None:
    """Parse CLI-provided target names."""

    if not raw_targets:
        return None

    parsed: set[SeedTarget] = set()
    for raw_target in raw_targets:
        try:
            parsed.add(SeedTarget(raw_target))
        except ValueError as exc:
            valid_targets = ", ".join(target.value for target in SEED_ORDER)
            raise ValueError(f"Unknown seed target {raw_target!r}. Expected one of: {valid_targets}") from exc
    return parsed


async def run_seed(session: AsyncSession, *, only: set[SeedTarget] | None = None) -> dict[SeedTarget, SeedOutcome]:
    """Seed the selected targets in dependency order."""

    selected_targets = only or set(SEED_ORDER)
    summary: dict[SeedTarget, SeedOutcome] = {}

    for target in SEED_ORDER:
        if target not in selected_targets:
            continue
        logger.info("Seeding %s", target.value)
        if target is SeedTarget.GEOGRAPHIES:
            summary[target] = await seed_geographies(session)
        elif target is SeedTarget.GEOGRAPHY_MEMBERSHIPS:
            summary[target] = await seed_geography_memberships(session)
        elif target is SeedTarget.TAGS:
            summary[target] = await seed_tags(session)
        elif target is SeedTarget.PROVIDERS:
            summary[target] = await seed_providers(session)
        elif target is SeedTarget.PROVIDER_CATALOGS:
            summary[target] = await seed_provider_catalogs(session)

    return summary


async def reset_seed_tables(session: AsyncSession, *, only: set[SeedTarget] | None = None) -> None:
    """Delete seed-managed rows in reverse dependency order."""

    selected_targets = only or set(RESET_ORDER)
    for target in RESET_ORDER:
        if target not in selected_targets:
            continue
        logger.warning("Resetting %s", target.value)
        if target is SeedTarget.PROVIDER_CATALOGS:
            await session.execute(delete(ProviderCatalog))
        elif target is SeedTarget.PROVIDERS:
            await session.execute(delete(Provider))
        elif target is SeedTarget.TAGS:
            await session.execute(delete(Tag))
        elif target is SeedTarget.GEOGRAPHY_MEMBERSHIPS:
            await session.execute(delete(GeographyMembership))
        elif target is SeedTarget.GEOGRAPHIES:
            await session.execute(delete(Geography))
    await session.flush()


__all__ = ["SEED_ORDER", "SeedTarget", "parse_seed_targets", "reset_seed_tables", "run_seed"]
