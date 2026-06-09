"""Shared async test fixtures for the seeded test database."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
import os

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from macro_foundry.backend.deps import get_session
from macro_foundry.backend.main import app
from macro_foundry.config import settings
from macro_foundry.seed import run_seed

_TRUNCATE_ALL_TABLES_SQL = """
TRUNCATE TABLE
    change_proposal_items,
    change_proposals,
    observations,
    computation_run_logs,
    ingestion_run_logs,
    derivation_inputs,
    derived_series,
    ingestion_feed_members,
    ingestion_feeds,
    series_sources,
    series_tags,
    series_family_members,
    series_families,
    series,
    provider_catalogs,
    providers,
    geography_memberships,
    tags,
    concepts,
    geographies
RESTART IDENTITY CASCADE
"""


def _owner_test_url() -> str:
    owner_url = make_url(settings.db.owner_url)
    test_url = make_url(settings.db.test_url)
    resolved_url: URL = owner_url.set(database=test_url.database)
    return resolved_url.render_as_string(hide_password=False)


def _alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config


async def _truncate_all_tables(url: str) -> None:
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql(_TRUNCATE_ALL_TABLES_SQL)
    finally:
        await engine.dispose()


async def _seed_test_database(url: str) -> None:
    engine = create_async_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        async with session_factory() as session:
            await run_seed(session)
            await session.commit()
    finally:
        await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_test_db(request: pytest.FixtureRequest) -> Iterator[None]:
    selected_items = getattr(request.session, "items", ())
    if selected_items and all(item.get_closest_marker("no_db") for item in selected_items):
        yield
        return

    original_owner_url = settings.db_owner_url
    owner_test_url = _owner_test_url()

    os.environ["MACRODB_OWNER_URL"] = owner_test_url
    settings.db_owner_url = owner_test_url
    settings.__dict__.pop("db", None)

    config = _alembic_config(owner_test_url)
    command.upgrade(config, "head")
    asyncio.run(_truncate_all_tables(owner_test_url))
    asyncio.run(_seed_test_database(settings.db.test_url))
    yield

    settings.db_owner_url = original_owner_url
    settings.__dict__.pop("db", None)
    os.environ["MACRODB_OWNER_URL"] = original_owner_url


@pytest.fixture(scope="session")
def alembic_config(migrated_test_db: None) -> Config:
    return _alembic_config(_owner_test_url())


@pytest_asyncio.fixture(scope="session")
async def owner_test_engine(migrated_test_db: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_owner_test_url(), pool_pre_ping=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def test_engine(migrated_test_db: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        settings.db.test_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_connection(test_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()


@pytest.fixture
def test_session_factory(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=db_connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )


@pytest_asyncio.fixture
async def session(test_session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with test_session_factory() as db_session:
        yield db_session


@pytest_asyncio.fixture
async def client(test_session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with test_session_factory() as db_session:
            try:
                yield db_session
            except Exception:
                await db_session.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.api.bearer_token.get_secret_value()}"}
