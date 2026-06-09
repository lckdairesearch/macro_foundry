# Project Overview

## What macro_foundry is

`macro_foundry` is a macroeconomic database system: a curated, vintage-aware,
provider-agnostic store of economic time series, plus the tooling around it.
It is built to be the data layer of a larger macro research workflow — eventually
serving independent macro researchers, sub-institutional funds, solo quants, and
AI agent developers who are priced out of enterprise tools like Macrobond or Haver.

The **system** is `macro_foundry`. The **logical database** inside it is
`macrodb`. Physical Postgres database names are environment-specific:
`macrodb_dev` and `macrodb_test` locally, `macrodb_prod` in cloud production.

## What problem it solves

Existing macroeconomic data sources fall into two camps:

- **Free but raw** — FRED, World Bank, IMF, OECD. Excellent data, but each has its
  own schema, identifiers, units, and frequency conventions. Combining them is a
  manual integration project for every new analysis.
- **Curated but expensive** — Macrobond, Haver, Refinitiv. Solve the integration
  problem but cost $20k+/year per seat and are not designed for programmatic
  research workflows or AI consumption.

`macro_foundry` curates a canonical layer on top of the free providers: a unified
schema for series, observations with vintage tracking, families that group
country-equivalent series, derived series with explicit lineage, and a governance
layer for proposed changes.

## Current phase — scope

This phase builds the **database layer and backend skeleton**. Specifically:

- Postgres 18.4 in Docker locally (`macrodb_dev` + `macrodb_test`), deploy-ready
  for Neon production as `macrodb_prod` (PG 18 default).
- Two roles: `macrodb_owner` for migrations, `macrodb_app` for everything else.
- All current schema tables as async SQLAlchemy models, including canonical
  `series_hierarchy_edges` and `ingestion_feed_members`.
- Alembic migrations including the `latest_observations` view.
- Pydantic schemas (Base / Create / Update / Read pattern) for every table.
- FastAPI routes: a thin in-repo CRUD generator for ~80% of tables,
  hand-tuned routes for `series` and `observations`.
- SQLAdmin mounted under `/admin` with basic auth.
- Typer CLI for seeding (`uv run macrodb seed`).
- Idempotent seed data for geographies, tags, and default providers/provider catalogs.
- A focused test suite (~28 tests) covering migrations, seed idempotency,
  the CRUD generator, constraint enforcement, hand-tuned routes, and one
  end-to-end smoke test.

## Definition of done for this phase

On a fresh clone, this sequence succeeds end-to-end:

```bash
docker compose --env-file .env.local up -d
uv sync
alembic upgrade head
uv run macrodb seed
uv run pytest
```

And the same five commands succeed when `MACRODB_OWNER_URL` and `MACRODB_APP_URL`
point at the cloud production database `macrodb_prod` on a Neon project — no
code changes, no restructuring, no skipped tests.

## Explicitly out of scope for this phase

- **Ingestion fetchers.** The `ingestion/` package will be scaffolded, but the
  actual HTTP clients for FRED, World Bank, Alpha Vantage, IMF are next phase.
- **The AI agent (LangGraph dual-researcher pattern).** Schema and the
  `change_proposals` / `change_proposal_items` tables are in scope; the agent
  that proposes into them is later.
- **Frontend.** No Next.js, no Tremor, no UI work. SQLAdmin is the only UI surface
  for now.
- **External ingestion fetchers beyond the FRED bootstrap path.** ADR 0010's
  request-level feed catalog, member-level run outcomes, and member-level
  observation provenance are implemented, but general provider HTTP clients for
  World Bank, IMF, OECD, and others remain next-phase work.
- **Materialized views, performance tuning, advanced indexing.** Add indexes only
  when a query justifies them, not pre-emptively.
- **Multi-tenant features, billing, public API gateway.** Not relevant yet.

## Who is the user

A single macro researcher (and one or two agents working on their behalf) using
the system locally, with the intent to host on Neon for production later. Local
Docker is the development environment, `macrodb_test` is the local test
environment, and cloud production is a separate environment. No external users,
no public API, no auth beyond basic-auth and a single bearer token, for this
phase.

## Why this scope, in this order

The schema is the hardest, longest-lived asset in the system. Getting it solid
before the agent, the frontend, or the ingestion fetchers is built means those
later layers consume a stable surface. Building them in parallel would force
schema revisions to ripple through unfinished code.
