"""Issue #79: the V8 categories tree (categories + category_edges).

End-to-end coverage of ADR 0025 §1/§2/§5: CRUD over the tree, recursive-CTE
ancestor/descendant walks through the read API, the strict-tree
`UNIQUE(child_category_id)` and no-self-edge guards, the named `kind` CHECK,
eager-loaded relationships, and `categories` as a governance target_type. These
run against the migrated, seeded macrodb_test harness.
"""

from __future__ import annotations

from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.enums import (
    Action,
    CategoryKind,
    ItemType,
    ProposalStatus,
    ProposalType,
    RequestedBy,
    RiskLevel,
    TargetType,
    ValidationStatus,
)
from macro_foundry.models import Category, CategoryEdge, ChangeProposal, ChangeProposalItem


async def _create_category(
    client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    code: str,
    name: str,
    kind: CategoryKind,
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/categories/",
        headers=auth_headers,
        json={"code": code, "name": name, "kind": kind.value},
    )
    assert response.status_code == HTTPStatus.CREATED
    return response.json()


async def _create_edge(
    client: AsyncClient,
    auth_headers: dict[str, str],
    *,
    parent_id: str,
    child_id: str,
) -> None:
    response = await client.post(
        "/api/v1/category-edges/",
        headers=auth_headers,
        json={"parent_category_id": parent_id, "child_category_id": child_id},
    )
    assert response.status_code == HTTPStatus.CREATED


@pytest.mark.asyncio
async def test_create_and_get_category(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await _create_category(
        client,
        auth_headers,
        code="CPI_ALL_ITEMS",
        name="CPI, all items",
        kind=CategoryKind.CONCEPT,
    )

    response = await client.get(f"/api/v1/categories/{created['id']}", headers=auth_headers)

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["code"] == "CPI_ALL_ITEMS"
    assert body["kind"] == "concept"


@pytest.mark.asyncio
async def test_ancestors_and_descendants_walk_the_tree(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    prices = await _create_category(client, auth_headers, code="PRICES", name="Prices", kind=CategoryKind.TOPIC)
    consumer = await _create_category(
        client, auth_headers, code="CONSUMER_PRICES", name="Consumer prices", kind=CategoryKind.TOPIC
    )
    cpi = await _create_category(
        client, auth_headers, code="CPI_ALL_ITEMS", name="CPI, all items", kind=CategoryKind.CONCEPT
    )
    await _create_edge(client, auth_headers, parent_id=prices["id"], child_id=consumer["id"])
    await _create_edge(client, auth_headers, parent_id=consumer["id"], child_id=cpi["id"])

    ancestors = await client.get(f"/api/v1/categories/{cpi['id']}/ancestors", headers=auth_headers)
    assert ancestors.status_code == HTTPStatus.OK
    assert [row["code"] for row in ancestors.json()] == ["CONSUMER_PRICES", "PRICES"]

    descendants = await client.get(f"/api/v1/categories/{prices['id']}/descendants", headers=auth_headers)
    assert descendants.status_code == HTTPStatus.OK
    assert [row["code"] for row in descendants.json()] == ["CONSUMER_PRICES", "CPI_ALL_ITEMS"]


@pytest.mark.asyncio
async def test_ancestors_of_missing_node_is_404(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    from uuid import uuid4

    response = await client.get(f"/api/v1/categories/{uuid4()}/ancestors", headers=auth_headers)

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_second_parent_rejected_by_unique_child(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    parent_a = await _create_category(client, auth_headers, code="PARENT_A", name="A", kind=CategoryKind.TOPIC)
    parent_b = await _create_category(client, auth_headers, code="PARENT_B", name="B", kind=CategoryKind.TOPIC)
    child = await _create_category(client, auth_headers, code="CHILD", name="Child", kind=CategoryKind.CONCEPT)

    await _create_edge(client, auth_headers, parent_id=parent_a["id"], child_id=child["id"])

    second = await client.post(
        "/api/v1/category-edges/",
        headers=auth_headers,
        json={"parent_category_id": parent_b["id"], "child_category_id": child["id"]},
    )

    assert second.status_code == HTTPStatus.CONFLICT


@pytest.mark.asyncio
async def test_self_edge_rejected_by_schema(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    node = await _create_category(client, auth_headers, code="SOLO", name="Solo", kind=CategoryKind.CONCEPT)

    response = await client.post(
        "/api/v1/category-edges/",
        headers=auth_headers,
        json={"parent_category_id": node["id"], "child_category_id": node["id"]},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_self_edge_rejected_by_db_check(session: AsyncSession) -> None:
    node = Category(code="SOLO_DB", name="Solo", kind=CategoryKind.CONCEPT)
    session.add(node)
    await session.flush()

    session.add(CategoryEdge(parent_category_id=node.id, child_category_id=node.id))
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
async def test_invalid_kind_rejected_by_named_check(session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "INSERT INTO categories (id, code, name, kind) "
                "VALUES (uuidv7(), 'BOGUS', 'Bogus', 'bucket')"
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_relationships_eager_load(session: AsyncSession) -> None:
    parent = Category(code="EAGER_PARENT", name="Parent", kind=CategoryKind.TOPIC)
    child = Category(code="EAGER_CHILD", name="Child", kind=CategoryKind.CONCEPT)
    session.add_all([parent, child])
    await session.flush()
    session.add(CategoryEdge(parent_category_id=parent.id, child_category_id=child.id))
    await session.flush()
    session.expire_all()

    loaded_parent = await session.scalar(select(Category).where(Category.id == parent.id))
    loaded_child = await session.scalar(select(Category).where(Category.id == child.id))

    # selectin-loaded; accessing does not raise MissingGreenlet.
    assert [edge.child_category_id for edge in loaded_parent.child_edges] == [child.id]
    assert loaded_child.parent_edge is not None
    assert loaded_child.parent_edge.parent_category_id == parent.id


@pytest.mark.asyncio
async def test_categories_embedding_column_and_hnsw_index_exist(session: AsyncSession) -> None:
    column_udt = await session.scalar(
        text(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'categories' AND column_name = 'embedding'"
        )
    )
    assert column_udt == "vector"

    index_def = await session.scalar(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_categories_embedding_hnsw'")
    )
    assert index_def is not None
    assert "USING hnsw" in index_def
    assert "vector_cosine_ops" in index_def


@pytest.mark.asyncio
async def test_categories_accepted_as_target_type(session: AsyncSession) -> None:
    proposal = ChangeProposal(
        title="issue-79 categories target_type probe",
        proposal_type=ProposalType.SCHEMA_CHANGE,
        status=ProposalStatus.PROPOSED,
        requested_by=RequestedBy.AGENT,
        risk_level=RiskLevel.LOW,
    )
    session.add(proposal)
    await session.flush()

    session.add(
        ChangeProposalItem(
            proposal_id=proposal.id,
            item_type=ItemType.DB_ROW,
            target_type=TargetType.CATEGORIES,
            action=Action.INSERT,
            validation_status=ValidationStatus.PENDING,
        )
    )
    await session.commit()

    stored = await session.scalar(
        select(ChangeProposalItem).where(ChangeProposalItem.proposal_id == proposal.id)
    )
    assert stored is not None
    assert stored.target_type is TargetType.CATEGORIES
