"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from macro_foundry.backend import admin as admin_module
from macro_foundry.backend.api import API_ROUTERS
from macro_foundry.backend.deps import get_session
from macro_foundry.db import async_engine, build_session_dependency, create_async_engine_for_url, create_session_factory


def _package_version() -> str:
    try:
        return version("macro-foundry")
    except PackageNotFoundError:
        return "0.1.0"


def create_app(*, database_url: str | None = None) -> FastAPI:
    """Build the FastAPI app, optionally targeting a non-default database URL."""

    engine: AsyncEngine = async_engine
    custom_engine = False
    if database_url is not None:
        engine = create_async_engine_for_url(database_url)
        custom_engine = True

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if custom_engine:
            await engine.dispose()

    app = FastAPI(
        title="macro_foundry API",
        version=_package_version(),
        lifespan=lifespan,
    )

    if custom_engine:
        session_factory = create_session_factory(engine)
        app.dependency_overrides[get_session] = build_session_dependency(session_factory)

    for router in API_ROUTERS:
        app.include_router(router, prefix="/api/v1")

    admin = admin_module.register_admin(app, engine=engine)
    app.state.admin = admin
    app.state.database_url = database_url

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        """Minimal process-health endpoint."""

        return {"status": "ok"}

    return app


app = create_app()
admin = app.state.admin


__all__ = ["admin", "app", "create_app"]
