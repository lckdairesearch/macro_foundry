"""FastAPI application entrypoint."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI

from macro_foundry.backend.api import API_ROUTERS


def _package_version() -> str:
    try:
        return version("macro-foundry")
    except PackageNotFoundError:
        return "0.1.0"


app = FastAPI(
    title="macro_foundry API",
    version=_package_version(),
)

for router in API_ROUTERS:
    app.include_router(router, prefix="/api/v1")


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    """Minimal process-health endpoint."""

    return {"status": "ok"}


__all__ = ["app"]
