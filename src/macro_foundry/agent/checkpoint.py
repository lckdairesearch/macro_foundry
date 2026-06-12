"""LangGraph checkpoint wiring for onboarding sessions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url

from macro_foundry.db import EnvTarget, app_url_for_target


def psycopg_langgraph_url(database_url: str) -> str:
    """Convert a SQLAlchemy psycopg URL to a psycopg URI scoped to langgraph."""

    url = make_url(database_url)
    if url.drivername == "postgresql+psycopg":
        url = url.set(drivername="postgresql")
    query = dict(url.query)
    query["options"] = "-c search_path=langgraph"
    conn_string = url.set(query=query).render_as_string(hide_password=False)
    return conn_string.replace("options=-c+search_path", "options=-c%20search_path")


@asynccontextmanager
async def postgres_checkpointer_for_target(
    target: EnvTarget,
) -> AsyncIterator[AsyncPostgresSaver]:
    """Open the PostgresSaver configured for one onboarding target."""

    conn_string = psycopg_langgraph_url(app_url_for_target(target))
    async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
        yield saver


__all__ = [
    "postgres_checkpointer_for_target",
    "psycopg_langgraph_url",
]
