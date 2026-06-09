"""Register SQLAdmin views on the FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI
from sqladmin import Admin
from sqlalchemy.ext.asyncio import AsyncEngine

from macro_foundry.backend.admin.auth import BasicAuthBackend
from macro_foundry.backend.admin.views import ADMIN_VIEWS
from macro_foundry.db.session import async_engine


def register_admin(app: FastAPI, *, engine: AsyncEngine | None = None) -> Admin:
    """Mount SQLAdmin and register the project's model views."""

    admin = Admin(
        app,
        engine=engine or async_engine,
        base_url="/admin",
        title="macro_foundry Admin",
        authentication_backend=BasicAuthBackend(),
    )
    for view in ADMIN_VIEWS:
        admin.add_view(view)
    return admin


__all__ = ["register_admin"]
