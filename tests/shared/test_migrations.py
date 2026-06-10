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
    "ingestion_feed_members",
    "ingestion_feeds",
    "ingestion_run_log_members",
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

            schema_owner = (
                await conn.exec_driver_sql(
                    """
                    SELECT pg_catalog.pg_get_userbyid(nspowner)
                    FROM pg_catalog.pg_namespace
                    WHERE nspname = 'langgraph'
                    """,
                )
            ).scalar_one()
            can_use = (
                await conn.exec_driver_sql(
                    """
                    SELECT has_schema_privilege('macrodb_app', 'langgraph', 'USAGE')
                    """,
                )
            ).scalar_one()
            can_insert_checkpoints = (
                await conn.exec_driver_sql(
                    """
                    SELECT has_table_privilege('macrodb_app', 'langgraph.checkpoints', 'INSERT')
                    """,
                )
            ).scalar_one()
            can_update_writes = (
                await conn.exec_driver_sql(
                    """
                    SELECT has_table_privilege('macrodb_app', 'langgraph.checkpoint_writes', 'UPDATE')
                    """,
                )
            ).scalar_one()
            can_delete_blobs = (
                await conn.exec_driver_sql(
                    """
                    SELECT has_table_privilege('macrodb_app', 'langgraph.checkpoint_blobs', 'DELETE')
                    """,
                )
            ).scalar_one()
            can_create = (
                await conn.exec_driver_sql(
                    """
                    SELECT has_schema_privilege('macrodb_app', 'langgraph', 'CREATE')
                    """,
                )
            ).scalar_one()

            assert EXPECTED_TABLES <= table_names
            assert table_names - EXPECTED_TABLES == {"alembic_version"}
            assert view_names == {"latest_observations"}
            assert schema_owner == "macrodb_owner"
            assert can_use is True
            assert can_insert_checkpoints is True
            assert can_update_writes is True
            assert can_delete_blobs is True
            assert can_create is False

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
