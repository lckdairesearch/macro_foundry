"""Async SQLAlchemy engine and session helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from macro_foundry.config import settings


def create_async_engine_for_url(url: str) -> AsyncEngine:
    """Create an async engine with the project's standard settings."""

    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create an async sessionmaker with the project's standard settings."""

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def build_session_dependency(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Build a FastAPI dependency that yields sessions from one factory."""

    async def _get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    return _get_session


async_engine = create_async_engine_for_url(settings.db.app_url)
AsyncSessionLocal = create_session_factory(async_engine)
get_session = build_session_dependency(AsyncSessionLocal)


__all__ = [
    "AsyncSessionLocal",
    "async_engine",
    "build_session_dependency",
    "create_async_engine_for_url",
    "create_session_factory",
    "get_session",
]
