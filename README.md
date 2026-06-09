# macro_foundry

An ambitious, long-running personal project to build the macroeconomic analysis stack I wish existed: a curated canonical database, an agent that grows it safely, nowcasting on top, and a frontend to drive it all.

## What it is

A canonical macro database designed for code and AI consumers, with the surrounding tooling to grow and use it. Series have semantic identifiers (`US_CPI_CORE_M_SA_LEVEL`) instead of provider tickers, every observation is vintage-tracked, and changes to the catalog are gated through a structured review workflow. On top of that foundation the eventual system includes a chat-style onboarding agent (in implementation), a nowcasting layer, and a web frontend.

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

| Component | State |
|---|---|
| `macrodb` — curated database, FastAPI, SQLAdmin, seed, FRED bootstrap | Built and working locally; Neon parity next |
| Gated onboarding agent | Designed (ADRs 0011 / 0012, issue [#19](https://github.com/lckdairesearch/macro_foundry/issues/19)); implementation in progress |
| Nowcasting | Planned; not started |
| Frontend | Planned; not started |

This is a single-operator project built in phases. The database is the foundation everything else lands on, so it gets built and stabilized first.

## Stack

Postgres 18 · async SQLAlchemy (psycopg3) · Alembic · FastAPI · SQLAdmin · Typer · uv

## Where to dig deeper

- [docs/project_overview.md](docs/project_overview.md) — what this is, in more depth
- [docs/architecture.md](docs/architecture.md) — the stack and the decisions behind it
- [CONTEXT.md](CONTEXT.md) — domain glossary (series vs concept vs observation, etc.)
- [docs/adr/](docs/adr/) — every architectural decision, with reasoning
- [docs/build_plan.md](docs/build_plan.md) and [docs/progress_tracker.md](docs/progress_tracker.md) — what's done and what's next

---

A single-operator research project. No public API, no SLA, no support. The code is the documentation; the ADRs are the rationale.
