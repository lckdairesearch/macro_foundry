"""`macrodb serve api` and `macrodb serve mcp` commands."""

from __future__ import annotations

from typing import Annotated

import typer

from macro_foundry.db import EnvTarget, database_url_for_env_target

from ._app import serve_app

_DEV_OR_TEST = {EnvTarget.DEV, EnvTarget.TEST}


@serve_app.command("api")
def serve_api(
    target: Annotated[
        EnvTarget,
        typer.Option("--target", case_sensitive=False, help="Target dev or test database."),
    ] = EnvTarget.DEV,
    host: Annotated[
        str,
        typer.Option("--host", help="Host interface to bind the API server to."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", min=1, max=65535, help="Port to bind the API server to."),
    ] = 8000,
    reload: Annotated[
        bool,
        typer.Option("--reload/--no-reload", help="Enable auto-reload (opt-in for local development)."),
    ] = False,
) -> None:
    """Start the FastAPI application."""

    import uvicorn

    if target not in _DEV_OR_TEST:
        typer.echo(f"serve api does not support --target {target.value} (allowed: dev, test)", err=True)
        raise typer.Exit(code=2)

    if target is EnvTarget.DEV:
        uvicorn.run(
            "macro_foundry.backend.main:app",
            host=host,
            port=port,
            reload=reload,
        )
        return

    from macro_foundry.backend.main import create_app

    uvicorn.run(
        create_app(database_url=database_url_for_env_target(target)),
        host=host,
        port=port,
        reload=False,
    )


@serve_app.command("mcp")
def serve_mcp(
    target: Annotated[
        EnvTarget,
        typer.Option("--target", case_sensitive=False, help="Target dev, test, or staging database."),
    ] = EnvTarget.DEV,
    write: Annotated[
        bool,
        typer.Option("--write/--no-write", help="Enable write tools (default: read-only)."),
    ] = False,
    database_url: Annotated[
        str | None,
        typer.Option("--database-url", help="Override --target with an explicit async SQLAlchemy URL."),
    ] = None,
) -> None:
    """Run a macrodb MCP server over stdio."""

    from macro_foundry.mcp.server import build_read_only_server, build_write_enabled_server

    try:
        url = database_url or database_url_for_env_target(target)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    if write:
        build_write_enabled_server(url).run(transport="stdio")
    else:
        build_read_only_server(url).run(transport="stdio")
