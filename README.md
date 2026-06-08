# macro_foundry

A curated, vintage-aware macroeconomic database system for research workflows.

## Why

- Free macro data is powerful but fragmented across incompatible provider schemas.
- Enterprise tools solve the curation problem, but they are expensive and closed.
- `macro_foundry` aims to provide a canonical macro data layer that is easier to query, extend, and eventually build products on top of.

## What Works Now

- Postgres-backed `macrodb` schema with 19 V3 tables
- Async SQLAlchemy models, Alembic migrations, and Pydantic schemas
- FastAPI backend with table CRUD plus hand-written `series` and `observations` routes
- SQLAdmin mounted at `/admin`
- Idempotent seed data for geographies, memberships, tags, providers, and catalogs
- Local test suite covering migrations, seeds, constraints, API routes, admin auth, and an end-to-end smoke path

## Quick Start

```bash
cp .env.example .env.local
docker compose --env-file .env.local up -d
uv sync
alembic upgrade head
uv run macrodb seed
uv run macrodb serve
```

Then open:

- API docs: `http://127.0.0.1:8000/docs`
- Admin: `http://127.0.0.1:8000/admin`

## How To Use It Today

- Seed the local database: `uv run macrodb seed`
- Start the backend: `uv run macrodb serve`
- Run the test suite: `uv run pytest`
- Browse the API schema in Swagger UI at `/docs`
- Log into SQLAdmin at `/admin` with `MACRODB_ADMIN_USERNAME` and `MACRODB_ADMIN_PASSWORD` from `.env.local`

## Status

This repo is in the backend skeleton phase, with Phases 0-12 complete and Phase 13 next: Neon parity verification.

What is in scope now:

- canonical schema and database plumbing
- local admin and API surfaces
- seed data and tests

What is not built yet:

- ingestion fetchers
- frontend product UI
- browser-safe public app API
- agent-driven proposal workflows

## Read More

- Project overview: [docs/project_overview.md](docs/project_overview.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- Progress tracker: [docs/progress_tracker.md](docs/progress_tracker.md)
- Domain glossary: [CONTEXT.md](CONTEXT.md)
- ADR index: [docs/adr/README.md](docs/adr/README.md)
- Agent instructions: [AGENTS.md](AGENTS.md)
