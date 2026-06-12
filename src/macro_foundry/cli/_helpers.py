"""Shared CLI helpers for the macrodb command surface (ADR 0017)."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Any, TypeVar

import typer

from macro_foundry.db import EnvTarget, app_url_for_target, create_async_engine_for_url, create_session_factory
from macro_foundry.seed import parse_seed_targets, reset_seed_tables, run_seed

F = TypeVar("F", bound=Callable[..., Any])


def cli_error_handler(func: F) -> F:
    """Catch ValueError and convert to Exit(2) with the message on stderr."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc

    return wrapper  # type: ignore[return-value]


def confirm_destructive(yes: bool, prompt: str = "This is a destructive action. Continue?") -> None:
    """Prompt interactively unless -y/--yes was given."""

    if not yes:
        typer.confirm(prompt, abort=True)


def print_result(result: dict[str, Any], *, as_json: bool) -> None:
    """Print a result dict as one space-separated key=value line or as JSON."""

    if as_json:
        typer.echo(json.dumps(result))
    else:
        typer.echo(" ".join(f"{k}={v}" for k, v in result.items()))


async def _seed_database(
    *,
    target: EnvTarget,
    only: list[str] | None,
    dry_run: bool,
    reset: bool,
) -> dict[object, object]:
    url = app_url_for_target(target)
    engine = create_async_engine_for_url(url)
    session_factory = create_session_factory(engine)
    selected_targets = parse_seed_targets(only)

    async with session_factory() as session:
        try:
            if reset:
                await reset_seed_tables(session, only=selected_targets)
            summary = await run_seed(session, only=selected_targets)
            if dry_run:
                await session.rollback()
            else:
                await session.commit()
            return summary
        except Exception:
            await session.rollback()
            raise


async def _bootstrap_database(
    *,
    target: EnvTarget,
    reset: bool,
    preset: str,
) -> object:
    from macro_foundry.bootstrap import (
        reset_fred_us_macro_bootstrap,
        run_debug_smoke_bootstrap,
        run_fred_us_macro_bootstrap,
    )

    if preset == "debug-smoke":
        if reset:
            raise ValueError("debug-smoke does not support --reset")
        return await run_debug_smoke_bootstrap(target=target)
    if reset:
        return await reset_fred_us_macro_bootstrap(target=target)
    return await run_fred_us_macro_bootstrap(target=target)
