"""Unit tests for the admin_stats pure module."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.backend.admin.stats import AdminStats, admin_stats
from macro_foundry.enums import OriginType
from macro_foundry.models import Concept


@pytest.mark.asyncio
async def test_admin_stats_returns_correct_shape(session: AsyncSession) -> None:
    stats = await admin_stats(session)

    assert isinstance(stats, AdminStats)
    assert stats.concept_count >= 0
    assert stats.indicator_count >= 0
    assert stats.observation_count >= 0
    assert stats.provider_count >= 0
    assert stats.ingestion_feed_count >= 0


@pytest.mark.asyncio
async def test_admin_stats_origin_type_keys_cover_all_values(
    session: AsyncSession,
) -> None:
    stats = await admin_stats(session)

    assert set(stats.series_count_by_origin_type.keys()) == {ot.value for ot in OriginType}
    for count in stats.series_count_by_origin_type.values():
        assert count >= 0


@pytest.mark.asyncio
async def test_admin_stats_concept_count_reflects_mutation(
    session: AsyncSession,
) -> None:
    stats_before = await admin_stats(session)

    session.add(Concept(name="Stat Test Concept", code="TEST_STAT_CONCEPT_55"))
    await session.flush()

    stats_after = await admin_stats(session)
    assert stats_after.concept_count == stats_before.concept_count + 1
