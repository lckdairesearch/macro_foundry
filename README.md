# macro_foundry

A curated, vintage-aware macroeconomic database with a gated agent for onboarding new sources.

## What

`macro_foundry` is the system; `macrodb` is the canonical Postgres database inside it. The system has two halves:

- **Curated database.** A unified schema for series, observations with vintage tracking, provider-agnostic canonical identifiers, request-level ingestion feeds with member-level provenance, and canonical parent-child series hierarchies. All vintages are stored; the `latest_observations` view returns one row per (series, period) for current-best-estimate reads. Built on Postgres 18, async SQLAlchemy, Alembic, FastAPI, and SQLAdmin.
- **Gated onboarding agent (in implementation).** A chat-style CLI that drives a LangGraph state machine for onboarding new providers and canonical series. The researcher describes a source in natural language; the agent investigates the provider, drafts catalog rows plus selector configuration, runs three parallel reviewer specializations, and surfaces a structured approval gate before any writes. Catalog mutations land in a durable pre-prod environment (`macrodb_staging` on Neon), not in production. The agent never commits code; new ingestion selectors flow through a sandbox-and-promote path tied to gate approval.

The schema honors ADR 0010's request-level ingestion model: one upstream request can populate many logical series through `ingestion_feed_members`, member-level run outcomes are recorded against `ingestion_run_log_members`, and each observation points to the exact member-level extraction attempt that produced it.

## Why

Macroeconomic data is stuck between two unworkable extremes:

- **Free but raw.** FRED, World Bank, IMF, OECD, e-Stat, BIS, BOJ — excellent data, each with its own schema, identifiers, units, frequency conventions, and quirks. Combining them is a manual integration project for every analysis.
- **Curated but expensive.** Macrobond, Haver, Refinitiv — solve the integration problem, cost $20k+/year per seat, and are not designed for programmatic research workflows or AI consumption.

`macro_foundry` curates a canonical layer on top of the free providers and exposes it to programmatic and AI consumers. The two design commitments that follow from this:

- **Catalog identity is canonical and provider-agnostic.** `series.code` is semantic (`US_CPI_CORE_M_SA_LEVEL`), not a provider ticker. Provider tickers live on `series_sources.external_code`. Changing the provider for a series does not change the series.
- **Mutations to the canonical catalog are gated.** Silent agent-driven catalog drift is the failure mode that ruins research workflows downstream. Every change goes through proposal, parallel review, and structured approval, with full conversational and decision-trace history preserved for evals.

## Status

| Layer | State |
|---|---|
| Schema (V3 + V4 hierarchy + request-level ingestion) | ✅ Complete (Phases 0–12, Issues 12–18) |
| Migrations, models, Pydantic schemas | ✅ Complete |
| FastAPI routes + SQLAdmin | ✅ Complete |
| Seed data (geographies, blocs, tags, providers) | ✅ Complete |
| Local test suite | ✅ Complete (~80 passing tests) |
| FRED bootstrap path (single-provider stress test) | ✅ Complete |
| Neon parity verification (Phase 13) | ⏳ Next up |
| Gated onboarding agent | 🚧 PRD published; 11 vertical implementation slices on the issue tracker |
| Frontend | Not started; later |

The gated onboarding agent design landed across [ADR 0011](docs/adr/0011-gated-onboarding-graph.md) and [ADR 0012](docs/adr/0012-selector-registry-ingestion-runtime.md), with implementation tracked under [issue #19](https://github.com/lckdairesearch/macro_foundry/issues/19) and slices #20–#30. The current build can serve API and admin reads/writes against the canonical schema today; the agent makes that catalog growable by a researcher in a structured way.

## Quick start

```bash
cp .env.example .env.local            # fill in MACRODB_*, FRED_API_KEY, etc.
docker compose --env-file .env.local up -d
uv sync
alembic upgrade head
uv run macrodb seed
uv run macrodb serve
```

Then:

- API docs: `http://127.0.0.1:8000/docs`
- Admin: `http://127.0.0.1:8000/admin` (credentials from `.env.local`)

For the FRED bootstrap path:

```bash
uv run macrodb bootstrap fred-us-macro --database app
```

## Using it today

- Browse the API at `/docs` and the admin at `/admin`.
- Bootstrap a curated FRED preset to populate concepts, families, raw and derived series, and request-level feeds in one go.
- Run the test suite: `uv run pytest`.
- Inspect `macrodb_test` after a bootstrap dry-run by pointing the app at it: `uv run macrodb serve --database test`.

The agent CLI (`macrodb onboard`) is not yet implemented; it lands in slice [#21](https://github.com/lckdairesearch/macro_foundry/issues/21) and gains real onboarding behavior across slices [#22–#30](https://github.com/lckdairesearch/macro_foundry/issues/20).

## Environments

| Database | Hosted on | Role |
|---|---|---|
| `macrodb_dev` | Local Docker | Developer playground; reset on demand |
| `macrodb_test` | Local Docker | Pytest target; reset by test fixtures; never an onboarding target |
| `macrodb_staging` | Neon | Durable pre-prod target for the onboarding agent; first ingestion runs execute here |
| `macrodb_prod` | Neon | Production; mutated only via the separate promotion workflow |

`macrodb_staging` and the separate-from-prod promotion path are introduced by the agent work; the current build runs against `macrodb_dev`/`macrodb_test` locally and is ready for Neon `macrodb_prod` (Phase 13). See [docs/environments.md](docs/environments.md) for the rationale.

## Roadmap

**Now in flight** ([issue #19](https://github.com/lckdairesearch/macro_foundry/issues/19), slices [#20–#30](https://github.com/lckdairesearch/macro_foundry/issues/20)):
- Selector-registry ingestion runtime; FRED migrates off its bespoke runner.
- Chat-style CLI + LangGraph state machine + Postgres checkpointer.
- Custom `macrodb-mcp` server (read-only and write-enabled) as the catalog seam.
- Three parallel reviewer specializations (governance, data correctness, selector code).
- Structured approval gates with small-edit collision handling and dangerous-correction branch.
- First non-FRED selectors: `csv_column`, `censtatd_json` (HK CenStatD), `estat_value_filter` (JPN e-Stat).

**After the agent lands:**
- Broader provider coverage via the now-routine "add a selector, add config" pattern.
- Routine refresh scheduling (the layer that the onboarding workflow explicitly does not own).
- Promotion workflow from `macrodb_staging` to `macrodb_prod`.
- A web frontend on top of the same `Channel` abstraction used by the CLI.

**Explicitly out of scope for now:**
- Multi-tenant features, public API gateway, billing.
- Materialized views and performance tuning (added only when a real query justifies them).
- Cross-provider series identity auto-resolution and cross-concept hierarchy automation.

## Project layout

```
macro_foundry/
├── CLAUDE.md / AGENTS.md          # agent operating manual
├── CONTEXT.md                     # domain glossary
├── docs/
│   ├── adr/                       # architecture decision records
│   ├── skills/                    # lazy-loaded domain knowledge packs for the agent
│   ├── architecture.md
│   ├── build_plan.md
│   ├── environments.md
│   ├── series_catalog_governance.md
│   ├── series_onboarding_workflow.md
│   └── progress_tracker.md
├── src/macro_foundry/
│   ├── backend/                   # FastAPI app + SQLAdmin
│   ├── db/                        # async engine, session, base
│   ├── enums/                     # str-Enum classes for CHECK-constrained columns
│   ├── models/                    # SQLAlchemy ORM
│   ├── schemas/                   # Pydantic Base/Create/Update/Read
│   ├── seed/                      # idempotent curated seed data
│   ├── bootstrap/                 # FRED preset bootstrap path
│   ├── ingestion/                 # current provider runner; new runtime/ coming in slice #20
│   └── cli.py                     # Typer entry; macrodb onboard coming in slice #21
├── alembic/                       # migrations
├── tests/                         # ~80 tests, integration-style
└── docker/                        # local Postgres init
```

## Read more

- Project overview: [docs/project_overview.md](docs/project_overview.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- Environments: [docs/environments.md](docs/environments.md)
- Build plan: [docs/build_plan.md](docs/build_plan.md)
- Progress tracker: [docs/progress_tracker.md](docs/progress_tracker.md)
- Domain glossary: [CONTEXT.md](CONTEXT.md)
- ADR index: [docs/adr/README.md](docs/adr/README.md)
- Series catalog governance: [docs/series_catalog_governance.md](docs/series_catalog_governance.md)
- Series onboarding workflow: [docs/series_onboarding_workflow.md](docs/series_onboarding_workflow.md)
- Skills directory: [docs/skills/README.md](docs/skills/README.md)
- Agent operating manual: [AGENTS.md](AGENTS.md)

## Status disclaimer

This is a single-operator research project. There is no public API, no auth surface beyond basic auth + single bearer token, no SLA, no support contract. The code is the documentation; the ADRs are the rationale.
