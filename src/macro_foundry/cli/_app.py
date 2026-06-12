"""Root Typer applications for the macrodb CLI."""

from __future__ import annotations

import typer

app = typer.Typer(help="macrodb command-line interface.")
db_app = typer.Typer(help="Database management commands.")
embeddings_app = typer.Typer(help="Embedding maintenance commands.")
serve_app = typer.Typer(help="Server commands.")

app.add_typer(db_app, name="db")
app.add_typer(embeddings_app, name="embeddings")
app.add_typer(serve_app, name="serve")
