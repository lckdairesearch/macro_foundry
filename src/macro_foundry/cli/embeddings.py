"""`macrodb embeddings …` subcommands."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated

import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from macro_foundry.config import settings
from macro_foundry.db import EnvTarget, app_url_for_target, create_async_engine_for_url, create_session_factory
from macro_foundry.models import Concept, Series, SeriesFamily, SeriesFamilyMember
from macro_foundry.services.embeddings import (
    EMBEDDING_MODEL,
    compose_concept_embedding_input,
    compose_family_embedding_input,
    compose_series_embedding_input,
    embed_texts,
    hash_embedding_input,
)

from . import _helpers
from ._app import embeddings_app

_DEV_OR_STAGING = {EnvTarget.DEV, EnvTarget.STAGING}
type EmbedBatch = Callable[[Sequence[str]], Awaitable[list[list[float]]]]


def _openai_api_key() -> str | None:
    api_key = settings.llm.openai_api_key
    if api_key is None:
        return None
    return api_key.get_secret_value()


async def run_embeddings_backfill(
    *,
    target: EnvTarget,
    batch_size: int,
) -> dict[str, int]:
    url = app_url_for_target(target)
    engine = create_async_engine_for_url(url)
    session_factory = create_session_factory(engine)
    try:
        return await run_embeddings_backfill_with_session_factory(
            session_factory=session_factory,
            batch_size=batch_size,
        )
    finally:
        await engine.dispose()


async def run_embeddings_backfill_with_session_factory(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    batch_size: int = 50,
    embed_batch: EmbedBatch | None = None,
) -> dict[str, int]:
    embed = embed_batch or embed_texts

    async with session_factory() as session:
        concepts = list((await session.execute(select(Concept))).scalars().all())
        families = list(
            (
                await session.execute(
                    select(SeriesFamily).options(
                        selectinload(SeriesFamily.geography),
                        selectinload(SeriesFamily.concept),
                    ),
                )
            ).scalars().all(),
        )
        series = list(
            (
                await session.execute(
                    select(Series).options(
                        selectinload(Series.geography),
                        selectinload(Series.family_member)
                        .selectinload(SeriesFamilyMember.family)
                        .selectinload(SeriesFamily.concept),
                    ),
                )
            ).scalars().all(),
        )

        summary = {
            "concepts": await _backfill_table(
                session=session,
                rows=concepts,
                compose=compose_concept_embedding_input,
                embed=embed,
                batch_size=batch_size,
            ),
            "series_families": await _backfill_table(
                session=session,
                rows=families,
                compose=compose_family_embedding_input,
                embed=embed,
                batch_size=batch_size,
            ),
            "series": await _backfill_table(
                session=session,
                rows=series,
                compose=compose_series_embedding_input,
                embed=embed,
                batch_size=batch_size,
            ),
        }
        return summary


def _batched[T](items: Sequence[T], size: int) -> list[Sequence[T]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def _is_stale(row: object, expected_hash: str) -> bool:
    return (
        getattr(row, "embedding") is None
        or getattr(row, "embedding_model") != EMBEDDING_MODEL
        or getattr(row, "embedding_input_hash") != expected_hash
    )


async def _backfill_table[T](
    *,
    session: AsyncSession,
    rows: Sequence[T],
    compose: Callable[[T], str],
    embed: EmbedBatch,
    batch_size: int,
) -> int:
    stale_rows: list[tuple[T, str, str]] = []
    for row in rows:
        text = compose(row)
        expected_hash = hash_embedding_input(text)
        if _is_stale(row, expected_hash):
            stale_rows.append((row, text, expected_hash))

    for batch in _batched(stale_rows, batch_size):
        vectors = await embed([text for _, text, _ in batch])
        if len(vectors) != len(batch):
            raise ValueError("Embedding batch size mismatch")
        for (row, _, expected_hash), vector in zip(batch, vectors, strict=True):
            setattr(row, "embedding", vector)
            setattr(row, "embedding_model", EMBEDDING_MODEL)
            setattr(row, "embedding_input_hash", expected_hash)
        await session.flush()

    await session.commit()
    return len(stale_rows)


@embeddings_app.command("backfill")
@_helpers.cli_error_handler
def backfill(
    target: Annotated[
        EnvTarget,
        typer.Option("--target", case_sensitive=False, help="Target dev or staging database."),
    ] = EnvTarget.DEV,
) -> None:
    """Backfill stale semantic-search embeddings."""

    if target not in _DEV_OR_STAGING:
        typer.echo(
            f"embeddings backfill does not support --target {target.value} (allowed: dev, staging)",
            err=True,
        )
        raise typer.Exit(code=2)

    if _openai_api_key() is None:
        raise ValueError("OPENAI_API_KEY is required for embeddings backfill")

    summary = asyncio.run(
        run_embeddings_backfill(
            target=target,
            batch_size=50,
        ),
    )
    for table_name in ("concepts", "series_families", "series"):
        typer.echo(f"{table_name}: {summary[table_name]} stale -> embedded")
