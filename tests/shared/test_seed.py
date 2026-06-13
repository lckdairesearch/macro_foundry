"""Phase 12 coverage for seed idempotency."""

from __future__ import annotations

from typing import TypeAlias

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.models import Geography, GeographyMembership, Provider, ProviderCatalog, Tag
from macro_foundry.seed import SeedTarget, reset_seed_tables, run_seed
from macro_foundry.seed.data.geographies import BLOCS, COUNTRIES, SUBNATIONALS, SUBNATIONAL_REGIONS
from macro_foundry.seed.data.memberships import GEOGRAPHY_MEMBERSHIPS
from macro_foundry.seed.data.providers import PROVIDER_CATALOGS, PROVIDERS
from macro_foundry.seed.data.tags import TAGS

SeedCounts: TypeAlias = dict[str, int]

EXPECTED_SEED_COUNTS: SeedCounts = {
    "geographies": len(COUNTRIES) + len(BLOCS) + 1 + len(SUBNATIONALS) + len(SUBNATIONAL_REGIONS),
    "geography_memberships": len(GEOGRAPHY_MEMBERSHIPS),
    "tags": len(TAGS),
    "providers": len(PROVIDERS),
    "provider_catalogs": len(PROVIDER_CATALOGS),
}


async def _count_seed_tables(session: AsyncSession) -> SeedCounts:
    return {
        "geographies": await session.scalar(select(func.count()).select_from(Geography)) or 0,
        "geography_memberships": await session.scalar(select(func.count()).select_from(GeographyMembership)) or 0,
        "tags": await session.scalar(select(func.count()).select_from(Tag)) or 0,
        "providers": await session.scalar(select(func.count()).select_from(Provider)) or 0,
        "provider_catalogs": await session.scalar(select(func.count()).select_from(ProviderCatalog)) or 0,
    }


@pytest.mark.asyncio
async def test_seed_populates_expected_row_counts_after_reset(
    session: AsyncSession,
) -> None:
    await reset_seed_tables(session)
    await session.commit()

    summary = await run_seed(session)
    await session.commit()

    assert await _count_seed_tables(session) == EXPECTED_SEED_COUNTS
    assert summary[SeedTarget.GEOGRAPHIES].inserted == EXPECTED_SEED_COUNTS["geographies"]
    assert summary[SeedTarget.GEOGRAPHY_MEMBERSHIPS].inserted == EXPECTED_SEED_COUNTS["geography_memberships"]
    assert summary[SeedTarget.TAGS].inserted == EXPECTED_SEED_COUNTS["tags"]
    assert summary[SeedTarget.PROVIDERS].inserted == EXPECTED_SEED_COUNTS["providers"]
    assert summary[SeedTarget.PROVIDER_CATALOGS].inserted == EXPECTED_SEED_COUNTS["provider_catalogs"]


@pytest.mark.asyncio
async def test_seed_rerun_is_idempotent_for_row_counts(
    session: AsyncSession,
) -> None:
    before_counts = await _count_seed_tables(session)

    summary = await run_seed(session)
    await session.commit()

    assert await _count_seed_tables(session) == before_counts
    assert all(outcome.inserted == 0 for outcome in summary.values())


@pytest.mark.asyncio
async def test_seed_restores_modified_seeded_tag_by_code(
    session: AsyncSession,
) -> None:
    prices = await session.scalar(select(Tag).where(Tag.code == "PRICES"))
    assert prices is not None

    prices.name = "Prices (mutated)"
    await session.commit()

    summary = await run_seed(session, only={SeedTarget.TAGS})
    await session.commit()

    restored = await session.scalar(select(Tag).where(Tag.code == "PRICES"))
    assert restored is not None
    await session.refresh(restored)
    assert restored.name == "Prices"
    assert summary[SeedTarget.TAGS].updated > 0


@pytest.mark.asyncio
async def test_seed_restores_modified_seeded_geography(
    session: AsyncSession,
) -> None:
    usa = await session.scalar(select(Geography).where(Geography.code == "USA"))
    assert usa is not None

    usa.name = "United States (mutated)"
    await session.commit()

    summary = await run_seed(session, only={SeedTarget.GEOGRAPHIES})
    await session.commit()

    restored = await session.scalar(select(Geography).where(Geography.code == "USA"))
    assert restored is not None
    await session.refresh(restored)
    assert restored.name == "United States"
    assert summary[SeedTarget.GEOGRAPHIES].updated > 0
