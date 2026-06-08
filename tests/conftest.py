"""Shared async test fixtures for API route coverage."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
import os

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from macro_foundry.backend.deps import get_session
from macro_foundry.backend.main import app
from macro_foundry.config import settings


def _owner_test_url() -> str:
    owner_url = make_url(settings.db.owner_url)
    test_url = make_url(settings.db.test_url)
    resolved_url: URL = owner_url.set(database=test_url.database)
    return resolved_url.render_as_string(hide_password=False)


def _alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session", autouse=True)
def migrated_test_db() -> Iterator[None]:
    original_owner_url = settings.db_owner_url
    owner_test_url = _owner_test_url()

    os.environ["MACRODB_OWNER_URL"] = owner_test_url
    settings.db_owner_url = owner_test_url
    settings.__dict__.pop("db", None)

    config = _alembic_config(owner_test_url)
    command.upgrade(config, "head")
    yield

    settings.db_owner_url = original_owner_url
    settings.__dict__.pop("db", None)
    os.environ["MACRODB_OWNER_URL"] = original_owner_url


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


@pytest_asyncio.fixture(autouse=True)
async def clean_database(owner_test_engine: AsyncEngine) -> AsyncIterator[None]:
    truncate_sql = """
    TRUNCATE TABLE
        change_proposal_items,
        change_proposals,
        observations,
        computation_run_logs,
        ingestion_run_logs,
        derivation_inputs,
        derived_series,
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
    async with owner_test_engine.begin() as conn:
        await conn.execute(text(truncate_sql))
    yield
    async with owner_test_engine.begin() as conn:
        await conn.execute(text(truncate_sql))


@pytest_asyncio.fixture
async def session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as db_session:
        yield db_session


@pytest_asyncio.fixture
async def client(test_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as db_session:
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
