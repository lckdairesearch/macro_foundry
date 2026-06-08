"""Regression coverage for SQLAdmin routes."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from macro_foundry.backend.main import admin, app
from macro_foundry.config import settings
from macro_foundry.enums import CodeStandard, GeographyType
from macro_foundry.models import Geography

ADMIN_LIST_IDENTITIES = [view.identity for view in admin.views]


@pytest.fixture
def admin_test_session_maker(
    test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    session_maker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    monkeypatch.setattr(admin, "engine", test_engine)
    monkeypatch.setattr(admin, "session_maker", session_maker)
    for view in admin.views:
        monkeypatch.setattr(view, "session_maker", session_maker)
    yield


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ADMIN_LIST_IDENTITIES)
async def test_admin_list_routes_render(
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
async def test_admin_geography_list_renders(
    session: AsyncSession,
    admin_test_session_maker: None,
) -> None:
    session.add_all(
            [
                Geography(
                    code="USA",
                    name="United States",
                    type=GeographyType.COUNTRY,
                    code_standard=CodeStandard.ISO_3166_1,
                ),
                Geography(
                    code="JPN",
                    name="Japan",
                    type=GeographyType.COUNTRY,
                    code_standard=CodeStandard.ISO_3166_1,
                ),
            ]
        )
    await session.commit()

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
    assert "United States" in response.text
    assert "Japan" in response.text
