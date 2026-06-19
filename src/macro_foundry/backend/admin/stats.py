"""Pure admin statistics module — no SQLAdmin, FastAPI, or Starlette imports."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import OriginType
from macro_foundry.models import (
    IngestionFeed,
    Observation,
    Provider,
    Series,
)


@dataclass
class AdminStats:
    series_count_by_origin_type: dict[str, int]
    observation_count: int
    provider_count: int
    ingestion_feed_count: int


async def admin_stats(session: AsyncSession) -> AdminStats:
    observation_count = (
        await session.scalar(select(func.count()).select_from(Observation)) or 0
    )
    provider_count = await session.scalar(select(func.count()).select_from(Provider)) or 0
    ingestion_feed_count = (
        await session.scalar(select(func.count()).select_from(IngestionFeed)) or 0
    )

    rows = await session.execute(
        select(Series.origin_type, func.count()).group_by(Series.origin_type)
    )
    by_origin_type = {str(origin_type): count for origin_type, count in rows}
    series_count_by_origin_type = {
        ot.value: by_origin_type.get(ot.value, 0) for ot in OriginType
    }

    return AdminStats(
        series_count_by_origin_type=series_count_by_origin_type,
        observation_count=observation_count,
        provider_count=provider_count,
        ingestion_feed_count=ingestion_feed_count,
    )


__all__ = ["AdminStats", "admin_stats"]
