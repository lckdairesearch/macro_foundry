"""Integration tests for the admin landing page."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from macro_foundry.backend.main import admin, app
from macro_foundry.config import settings


@pytest.fixture
def admin_test_session_maker(
    test_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admin, "session_maker", test_session_factory)
    for view in admin.views:
        monkeypatch.setattr(view, "session_maker", test_session_factory)


@pytest.mark.asyncio
async def test_admin_landing_returns_200_with_auth(
    admin_test_session_maker: None,
) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await client.post(
            "/admin/login",
            data={
                "username": settings.admin.username,
                "password": settings.admin.password.get_secret_value(),
            },
            follow_redirects=False,
        )
        response = await client.get("/admin/")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_landing_contains_intro_headline(
    admin_test_session_maker: None,
) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await client.post(
            "/admin/login",
            data={
                "username": settings.admin.username,
                "password": settings.admin.password.get_secret_value(),
            },
            follow_redirects=False,
        )
        response = await client.get("/admin/")

    assert "macro_foundry Admin" in response.text


@pytest.mark.asyncio
async def test_admin_landing_contains_count_card_labels(
    admin_test_session_maker: None,
) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await client.post(
            "/admin/login",
            data={
                "username": settings.admin.username,
                "password": settings.admin.password.get_secret_value(),
            },
            follow_redirects=False,
        )
        response = await client.get("/admin/")

    assert "Series" in response.text
    assert "Observations" in response.text
    assert "Providers" in response.text
    assert "Ingestion Feeds" in response.text


@pytest.mark.asyncio
async def test_admin_landing_redirects_to_login_without_auth(
    admin_test_session_maker: None,
) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/admin/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")
