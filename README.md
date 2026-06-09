# macro_foundry

A curated, vintage-aware macroeconomic database with a gated agent for onboarding new sources.

## What it is

Macroeconomic data comes in two flavors: **free but raw** (FRED, World Bank, IMF, OECD, BIS…) where every provider has its own schema and quirks, and **curated but expensive** (Macrobond, Haver, Refinitiv) at $20k+/seat and not built for programmatic use.

`macro_foundry` is a third option: a canonical layer on top of the free providers, designed for code and AI consumers. Series have semantic identifiers (`US_CPI_CORE_M_SA_LEVEL`) instead of provider tickers, every observation is vintage-tracked, and changes to the catalog are gated through a structured review workflow.

## Try it

```bash
git clone https://github.com/lckdairesearch/macro_foundry && cd macro_foundry
cp .env.example .env.local            # add MACRODB_* and FRED_API_KEY
docker compose --env-file .env.local up -d
uv sync && alembic upgrade head
uv run macrodb seed
uv run macrodb bootstrap fred-us-macro --database app
uv run macrodb serve
```

Then open:
- **API docs** — http://127.0.0.1:8000/docs
- **Admin UI** — http://127.0.0.1:8000/admin

Run the test suite with `uv run pytest` (~80 tests).

## Status

The database half is built and working: schema, migrations, FastAPI, SQLAdmin, seed data, and a FRED bootstrap path that exercises it end-to-end. Local against Postgres 18; Neon parity verification is next.

The **gated onboarding agent** — a chat CLI that researches a new provider, drafts catalog rows, runs three parallel reviewers, and asks for approval before any write — is designed and on the issue tracker, not yet implemented. See [ADR 0011](docs/adr/0011-gated-onboarding-graph.md) and [issue #19](https://github.com/lckdairesearch/macro_foundry/issues/19).

No frontend yet.

## Stack

Postgres 18 · async SQLAlchemy (psycopg3) · Alembic · FastAPI · SQLAdmin · Typer · uv

## Where to dig deeper

- [docs/project_overview.md](docs/project_overview.md) — what this is, in more depth
- [docs/architecture.md](docs/architecture.md) — the stack and the decisions behind it
- [CONTEXT.md](CONTEXT.md) — domain glossary (series vs concept vs observation, etc.)
- [docs/adr/](docs/adr/) — every architectural decision, with reasoning
- [docs/build_plan.md](docs/build_plan.md) and [docs/progress_tracker.md](docs/progress_tracker.md) — what's done and what's next

---

This is a single-operator research project. No public API, no SLA, no support. The code is the documentation; the ADRs are the rationale.
