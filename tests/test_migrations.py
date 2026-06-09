"""Phase 12 coverage for the Alembic migration chain."""

from __future__ import annotations

import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from macro_foundry.config import settings
from macro_foundry.seed import run_seed

EXPECTED_TABLES = {
    "change_proposal_items",
    "change_proposals",
    "computation_run_logs",
    "concepts",
    "derivation_inputs",
    "derived_series",
    "geographies",
    "geography_memberships",
    "ingestion_feeds",
    "ingestion_run_logs",
    "observations",
    "provider_catalogs",
    "providers",
    "series",
    "series_families",
    "series_family_members",
    "series_hierarchy_edges",
    "series_sources",
    "series_tags",
    "tags",
}


async def _assert_round_trip_and_reseed() -> None:
    owner_engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)
    app_engine = create_async_engine(
        settings.db.test_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
    )
    session_factory = async_sessionmaker(
        bind=app_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    try:
        async with owner_engine.connect() as conn:
            table_rows = await conn.exec_driver_sql(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                """,
            )
            view_rows = await conn.exec_driver_sql(
                """
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = 'public'
                """,
            )

            table_names = {row[0] for row in table_rows}
            view_names = {row[0] for row in view_rows}

        assert EXPECTED_TABLES <= table_names
        assert table_names - EXPECTED_TABLES == {"alembic_version"}
        assert view_names == {"latest_observations"}

        async with session_factory() as session:
            await run_seed(session)
            await session.commit()
    finally:
        await owner_engine.dispose()
        await app_engine.dispose()


def test_alembic_round_trip_recreates_schema_and_view(
    alembic_config: Config,
) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    asyncio.run(_assert_round_trip_and_reseed())
