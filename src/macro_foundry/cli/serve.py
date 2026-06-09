"""`macrodb serve` command."""

from __future__ import annotations

import typer
import uvicorn

from macro_foundry.bootstrap import DatabaseTarget
from macro_foundry.db import database_url_for_target

from ._app import app


@app.command("serve")
def serve(
    host: str = typer.Option(
        default="127.0.0.1",
        help="Host interface to bind the API server to.",
    ),
    port: int = typer.Option(
        default=8000,
        min=1,
        max=65535,
        help="Port to bind the API server to.",
    ),
    database: DatabaseTarget = typer.Option(
        default=DatabaseTarget.APP,
        case_sensitive=False,
        help="Target the app or test database.",
    ),
    reload: bool = typer.Option(
        default=True,
        help="Enable auto-reload for local development.",
    ),
) -> None:
    """Start the FastAPI application with development defaults."""

    if database is DatabaseTarget.APP:
        uvicorn.run(
            "macro_foundry.backend.main:app",
            host=host,
            port=port,
            reload=reload,
        )
        return

    from macro_foundry.backend.main import create_app

    uvicorn.run(
        create_app(database_url=database_url_for_target(database)),
        host=host,
        port=port,
        reload=False,
    )
