"""Regression coverage for SQLAdmin authentication."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from macro_foundry.backend.main import admin, app
from macro_foundry.config import settings
from macro_foundry.models import Geography

ADMIN_LIST_IDENTITIES = [view.identity for view in admin.views]


@pytest.fixture
def admin_test_session_maker(
    test_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admin, "session_maker", test_session_factory)
    for view in admin.views:
        monkeypatch.setattr(view, "session_maker", test_session_factory)


@pytest.mark.asyncio
async def test_admin_redirects_to_login_when_not_authenticated(
    admin_test_session_maker: None,
) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/admin/geography/list", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ADMIN_LIST_IDENTITIES)
async def test_admin_list_routes_render_after_login(
    admin_test_session_maker: None,
    identity: str,
) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login_response = await client.post(
            "/admin/login",
            data={
                "username": settings.admin.username,
                "password": settings.admin.password.get_secret_value(),
            },
            follow_redirects=False,
        )
        assert login_response.status_code == 302

        response = await client.get(f"/admin/{identity}/list")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_login_grants_access_to_seeded_geographies(
    session: AsyncSession,
    admin_test_session_maker: None,
) -> None:
    usa = await session.scalar(select(Geography).where(Geography.code == "USA"))
    assert usa is not None

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login_response = await client.post(
            "/admin/login",
            data={
                "username": settings.admin.username,
                "password": settings.admin.password.get_secret_value(),
            },
            follow_redirects=False,
        )
        assert login_response.status_code == 302

        response = await client.get("/admin/geography/list")

    assert response.status_code == 200
    assert "/admin/geography/list" in response.text
