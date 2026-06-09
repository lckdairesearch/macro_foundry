"""Phase 12 coverage for the thin CRUD generator."""

from __future__ import annotations

from http import HTTPStatus
from uuid import uuid4

import pytest
from httpx import AsyncClient


async def _create_concept(
    client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    code: str = "MF_CPI",
    name: str = "Macro Foundry CPI",
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/concepts/",
        headers=auth_headers,
        json={"code": code, "name": name},
    )
    assert response.status_code == HTTPStatus.CREATED
    return response.json()


@pytest.mark.asyncio
async def test_list_concepts_returns_empty_collection(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get("/api/v1/concepts/", headers=auth_headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_concept_returns_created_row(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/v1/concepts/",
        headers=auth_headers,
        json={"code": "MF_GDP", "name": "Macro Foundry GDP"},
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["code"] == "MF_GDP"


@pytest.mark.asyncio
async def test_get_concept_returns_existing_row(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    concept = await _create_concept(client, auth_headers)

    response = await client.get(f"/api/v1/concepts/{concept['id']}", headers=auth_headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["code"] == concept["code"]


@pytest.mark.asyncio
async def test_get_concept_returns_not_found_for_unknown_id(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get(f"/api/v1/concepts/{uuid4()}", headers=auth_headers)

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_patch_concept_updates_existing_row(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    concept = await _create_concept(client, auth_headers)

    response = await client.patch(
        f"/api/v1/concepts/{concept['id']}",
        headers=auth_headers,
        json={"description": "Updated via CRUD generator"},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["description"] == "Updated via CRUD generator"


@pytest.mark.asyncio
async def test_delete_concept_removes_existing_row(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    concept = await _create_concept(client, auth_headers)

    delete_response = await client.delete(f"/api/v1/concepts/{concept['id']}", headers=auth_headers)
    get_response = await client.get(f"/api/v1/concepts/{concept['id']}", headers=auth_headers)

    assert delete_response.status_code == HTTPStatus.NO_CONTENT
    assert get_response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_list_concepts_supports_column_filters(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    await _create_concept(client, auth_headers, code="MF_CPI", name="Macro Foundry CPI")
    await _create_concept(client, auth_headers, code="MF_GDP", name="Macro Foundry GDP")

    response = await client.get(
        "/api/v1/concepts/",
        headers=auth_headers,
        params={"code": "MF_GDP"},
    )

    assert response.status_code == HTTPStatus.OK
    assert [row["code"] for row in response.json()] == ["MF_GDP"]


@pytest.mark.asyncio
async def test_list_concepts_rejects_unknown_filters(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/concepts/",
        headers=auth_headers,
        params={"unknown_filter": "value"},
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "Unsupported filters" in response.json()["detail"]
