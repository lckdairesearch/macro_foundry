"""Register SQLAdmin views on the FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from sqladmin import Admin
from sqladmin.authentication import login_required
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.requests import Request
from starlette.responses import Response

from macro_foundry.backend.admin.auth import BasicAuthBackend
from macro_foundry.backend.admin.stats import admin_stats
from macro_foundry.backend.admin.views import ADMIN_VIEWS
from macro_foundry.db.session import async_engine

_TEMPLATES_DIR = str(Path(__file__).parent / "templates")


class _MacroFoundryAdmin(Admin):
    """Admin subclass with a custom landing page replacing the stock index."""

    @login_required
    async def index(self, request: Request) -> Response:
        async with self.session_maker() as session:
            stats = await admin_stats(session)
        return await self.templates.TemplateResponse(
            request,
            "landing.html",
            {"stats": stats},
        )


def register_admin(app: FastAPI, *, engine: AsyncEngine | None = None) -> Admin:
    """Mount SQLAdmin and register the project's model views."""

    admin = _MacroFoundryAdmin(
        app,
        engine=engine or async_engine,
        base_url="/admin",
        title="macro_foundry Admin",
        authentication_backend=BasicAuthBackend(),
        templates_dir=_TEMPLATES_DIR,
    )
    for view in ADMIN_VIEWS:
        admin.add_view(view)
    return admin


__all__ = ["register_admin"]
