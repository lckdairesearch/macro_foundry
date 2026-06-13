"""Phase 12 coverage for the Alembic migration chain."""

from __future__ import annotations

import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import text
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
    "indicators",
    "indicator_variants",
    "series",
    "series_hierarchy_edges",
    "series_sources",
    "series_tags",
    "tags",
}

EMBEDDED_TABLES = ("concepts", "series", "indicators")
EMBEDDED_COLUMNS = ("embedding", "embedding_input_hash", "embedding_model")
VECTOR_LITERAL = "[" + ",".join(["0.1"] * 1536) + "]"


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


async def _reseed_test_database() -> None:
    app_engine = create_async_engine(settings.db.test_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(
        bind=app_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        async with session_factory() as session:
            await run_seed(session)
            await session.commit()
    finally:
        await app_engine.dispose()


async def _assert_catalog_embedding_schema() -> None:
    owner_engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)

    try:
        async with owner_engine.connect() as conn:
            extension_name = (
                await conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname = 'vector'"),
                )
            ).scalar_one_or_none()
            assert extension_name == "vector"

            column_rows = await conn.execute(
                text(
                    """
                    SELECT table_name, column_name, udt_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = ANY(:tables)
                      AND column_name = ANY(:columns)
                    ORDER BY table_name, column_name
                    """,
                ),
                {"tables": list(EMBEDDED_TABLES), "columns": list(EMBEDDED_COLUMNS)},
            )
            assert {
                (row.table_name, row.column_name, row.udt_name) for row in column_rows
            } == {
                ("concepts", "embedding", "vector"),
                ("concepts", "embedding_input_hash", "text"),
                ("concepts", "embedding_model", "text"),
                ("series", "embedding", "vector"),
                ("series", "embedding_input_hash", "text"),
                ("series", "embedding_model", "text"),
                ("indicators", "embedding", "vector"),
                ("indicators", "embedding_input_hash", "text"),
                ("indicators", "embedding_model", "text"),
            }

            index_rows = await conn.execute(
                text(
                    """
                    SELECT tablename, indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename = ANY(:tables)
                    """,
                ),
                {"tables": list(EMBEDDED_TABLES)},
            )
            index_defs_by_table = {
                row.tablename: row.indexdef
                for row in index_rows
                if "USING hnsw" in row.indexdef and "vector_cosine_ops" in row.indexdef
            }
            assert set(index_defs_by_table) == set(EMBEDDED_TABLES)

            concept_id = (
                await conn.execute(
                    text(
                        """
                        INSERT INTO concepts (
                            code,
                            name,
                            description,
                            embedding,
                            embedding_model,
                            embedding_input_hash
                        )
                        VALUES (
                            :code,
                            :name,
                            :description,
                            CAST(:embedding AS vector(1536)),
                            :embedding_model,
                            :embedding_input_hash
                        )
                        ON CONFLICT (code) DO UPDATE
                        SET name = EXCLUDED.name,
                            description = EXCLUDED.description,
                            embedding = EXCLUDED.embedding,
                            embedding_model = EXCLUDED.embedding_model,
                            embedding_input_hash = EXCLUDED.embedding_input_hash
                        RETURNING id
                        """,
                    ),
                    {
                        "code": "TEST_EMBEDDING_CONCEPT",
                        "name": "Test embedding concept",
                        "description": "Vector migration smoke test",
                        "embedding": VECTOR_LITERAL,
                        "embedding_model": "text-embedding-3-small",
                        "embedding_input_hash": "test-input-hash",
                    },
                )
            ).scalar_one()

            nearest_id = (
                await conn.execute(
                    text(
                        """
                        SELECT id
                        FROM concepts
                        WHERE embedding IS NOT NULL
                        ORDER BY embedding <=> CAST(:embedding AS vector(1536))
                        LIMIT 1
                        """,
                    ),
                    {"embedding": VECTOR_LITERAL},
                )
            ).scalar_one()
            assert nearest_id == concept_id
    finally:
        await owner_engine.dispose()


async def _assert_catalog_embedding_schema_removed_but_extension_persists() -> None:
    owner_engine = create_async_engine(settings.db.owner_url, pool_pre_ping=True)

    try:
        async with owner_engine.connect() as conn:
            extension_name = (
                await conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname = 'vector'"),
                )
            ).scalar_one_or_none()
            assert extension_name == "vector"

            column_rows = await conn.execute(
                text(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = ANY(:tables)
                      AND column_name = ANY(:columns)
                    """,
                ),
                {"tables": list(EMBEDDED_TABLES), "columns": list(EMBEDDED_COLUMNS)},
            )
            assert list(column_rows) == []

            index_rows = await conn.execute(
                text(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename = ANY(:tables)
                    """,
                ),
                {"tables": list(EMBEDDED_TABLES)},
            )
            hnsw_indexes = [
                row.indexname
                for row in index_rows
                if row.indexname in {
                    "ix_concepts_embedding_hnsw",
                    "ix_series_embedding_hnsw",
                    "ix_indicators_embedding_hnsw",
                }
            ]
            assert hnsw_indexes == []
    finally:
        await owner_engine.dispose()


def test_alembic_round_trip_recreates_schema_and_view(
    alembic_config: Config,
) -> None:
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    asyncio.run(_assert_round_trip_and_reseed())


def test_head_migration_adds_catalog_embedding_schema() -> None:
    asyncio.run(_assert_catalog_embedding_schema())


def test_downgrade_to_0011_removes_embedding_schema_but_keeps_extension(
    alembic_config: Config,
) -> None:
    command.downgrade(alembic_config, "0011")
    asyncio.run(_assert_catalog_embedding_schema_removed_but_extension_persists())

    command.upgrade(alembic_config, "head")
    asyncio.run(_assert_catalog_embedding_schema())
    # The downgrade/upgrade cycle truncates seeded data; restore it so this test
    # leaves the shared session database in the seeded state later tests expect.
    asyncio.run(_reseed_test_database())
