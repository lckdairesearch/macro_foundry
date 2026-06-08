# Build Plan

The implementation is split into 13 phases plus a Phase 0 for agent infrastructure.
Phases run roughly sequentially; some can overlap (e.g. Pydantic schemas can start
once the corresponding model is done).

Each phase declares:

- **Deliverables** — concrete artifacts produced
- **Depends on** — which phases must be complete first
- **Verify** — the command or check that proves the phase is done
- **Estimated effort** — rough size to set expectations

Update `progress_tracker.md` when a phase completes. Do not skip the verify step.

---

## Phase 0 — Agent infrastructure

**Status:** in progress (this is what's being set up now).

**Deliverables:**

- `CLAUDE.md` and `AGENTS.md` at the project root (identical content)
- `docs/project_overview.md`, `docs/architecture.md`, `docs/code_standards.md`,
  `docs/glossary.md`, `docs/build_plan.md`, `docs/progress_tracker.md`
- `docs/adr/0001` through `docs/adr/0006` (the decisions from the planning session)
- `docs/schema/db_er.txt` (V3 canonical schema)
- Matt Pocock skills installed: `grill-with-docs`, `tdd`, `diagnose`, `zoom-out`

**Depends on:** nothing.

**Verify:** All files listed above exist. Running an agent against the repo and
asking "what is macro_foundry?" produces an answer consistent with
`project_overview.md`.

---

## Phase 1 — Repo bootstrap

**Deliverables:**

- Directory skeleton matching `architecture.md`
- `pyproject.toml` with all dependencies, uv-managed
- `.gitignore`, `.env.example`, `.env.local` (gitignored)
- `README.md` skeleton (links to `CLAUDE.md`)
- `uv sync` succeeds, virtualenv set up

**Dependencies in pyproject.toml:**

- Runtime: `fastapi`, `sqlalchemy[asyncio]>=2.0`, `psycopg[binary]>=3.1`,
  `pydantic>=2`, `pydantic-settings`, `alembic`, `sqladmin`, `typer`,
  `python-jose[cryptography]`, `passlib[bcrypt]`, `python-multipart`,
  `itsdangerous` (for SQLAdmin session middleware)
- Dev: `pytest`, `pytest-asyncio`, `httpx`, `ruff`, `mypy`

**Depends on:** Phase 0.

**Verify:** `uv sync` exits 0. `uv run python -c "import macro_foundry"` succeeds
(empty package).

**Effort:** Half-day.

---

## Phase 2 — Docker + Postgres + roles

**Deliverables:**

- `docker-compose.yml` running Postgres 18.4 with persistent volume
- `docker/postgres/init/01_roles.sql` creating `macrodb_owner` and `macrodb_app`
  roles, both `macrodb` and `macrodb_test` databases, and the appropriate grants
- `.env.example` updated with `MACRODB_OWNER_URL`, `MACRODB_APP_URL`, `MACRODB_TEST_URL`

**Depends on:** Phase 1.

**Verify:** `docker compose up -d` succeeds. `psql $MACRODB_OWNER_URL -c '\du'`
shows both roles. `psql $MACRODB_APP_URL -c 'SELECT current_user'` confirms app
role connection.

**Effort:** Half-day.

---

## Phase 3 — Config + session + base

**Deliverables:**

- `src/macro_foundry/config.py` — pydantic-settings reading `.env.local`, with
  namespaced sub-settings (`settings.db.*`, `settings.admin.*`, `settings.api.*`)
- `src/macro_foundry/db/base.py` — declarative `Base` + `TimestampedBase` mixin
  - `CreatedAtBase` mixin
- `src/macro_foundry/db/session.py` — `async_engine`, `AsyncSessionLocal`,
  `get_session()` dependency. Engine configured per `code_standards.md`:
  `pool_pre_ping=True`, `pool_recycle=300`, `pool_size=5`, `max_overflow=10`,
  `expire_on_commit=False`.

**Depends on:** Phase 2.

**Verify:** `uv run python -c "from macro_foundry.db.session import async_engine;
import asyncio; from sqlalchemy import text; asyncio.run(async_engine.begin().__aenter__()
.execute(text('SELECT 1')))"` (or simpler script) connects successfully.

**Effort:** Half-day.

---

## Phase 4 — Enums

**Deliverables:**

- All V3 enum classes in `src/macro_foundry/enums/`, organized by domain:
  `geography.py`, `series.py`, `provider.py`, `derivation.py`, `run.py`,
  `governance.py`
- `src/macro_foundry/enums/__init__.py` re-exports the public surface

**Cross-reference for completeness:**

- `geography.py`: `GeographyType`, `CodeStandard`
- `series.py`: `OriginType`, `Frequency`, `TemporalStockFlow`, `UnitKind`,
  `UnitScale`, `PriceBasis`, `Measure`, `MeasureHorizon`, `SeasonalAdjustment`,
  `ReferenceKind`
- `provider.py`: `ProviderType`, `ProviderRole`, `FeedMethod`
- `derivation.py`: `ExecutionPolicy`, `InputVintagePolicy`, `OutputMode`
- `run.py`: `IngestionRunStatus`, `ComputationRunStatus`,
  `IngestionTriggeredBy`, `ComputationTriggeredBy`
- `governance.py`: `ProposalType`, `ProposalStatus`, `RequestedBy`, `RiskLevel`,
  `ItemType`, `TargetType`, `Action`, `ValidationStatus`

**Depends on:** Phase 1 (uses Python).

**Verify:** `uv run python -c "from macro_foundry.enums import Frequency;
print(Frequency.MONTHLY.value)"` prints `"M"`.

**Effort:** Half-day.

---

## Phase 5 — Models

**Deliverables:**

- All 19 V3 tables as SQLAlchemy models in `src/macro_foundry/models/`,
  grouped by domain (`geography.py`, `concept.py`, `tag.py`, `provider.py`,
  `series.py`, `observation.py`, `derived.py`, `ingestion.py`, `run_log.py`,
  `governance.py`)
- Every model has UNIQUE constraints, CHECK constraints (single-column via
  `Enum(native_enum=False)`, cross-column via `CheckConstraint` in
  `__table_args__`), FKs, and the three one-to-one UNIQUEs from V3's `-` notation
- Every FK declares explicit `ondelete=...` behavior aligned with ADR 0008 and
  the canonical relationships section in `docs/schema/db_er.txt`
- `src/macro_foundry/models/__init__.py` exports every model so Alembic sees
  the full metadata graph

**Cross-column CHECKs from V3 to implement:**

- `series`: `measure='growth'` → `measure_horizon IS NOT NULL`
- `series`: `unit_kind='currency'` → `currency_code IS NOT NULL`
- `observations`: `period_end >= period_start`
- `geographies`: `type IN ('subnational', 'subnational_region')` →
  `parent_geography_id IS NOT NULL`

**Intentionally NOT implemented (per V3 final draft):**

- `reference_kind` set → `reference_year IS NOT NULL`
- `series_family_members` partial unique on `(family_id) WHERE is_primary = true`

**One-to-one UNIQUE constraints:**

- `UNIQUE(replaced_by_series_id)` on `series`
- `UNIQUE(series_id)` on `series_family_members`
- `UNIQUE(series_id)` on `derived_series`

**Depends on:** Phases 3 and 4.

**Verify:** `uv run python -c "from macro_foundry.models import *;
from macro_foundry.db.base import Base; print(len(Base.metadata.tables))"`
prints `19`.

**Effort:** 1-2 days.

---

## Phase 6 — Alembic + initial migrations

**Deliverables:**

- `alembic.ini` configured
- `alembic/env.py` connects via `MACRODB_OWNER_URL`, imports `Base.metadata`
- Migration `0001_initial_schema.py` — autogenerated, **reviewed** to confirm:
  - All 19 tables created
  - All UNIQUE constraints present and named
  - All CHECK constraints (single-column + cross-column) present and named
  - All FKs present with ADR-0008-aligned `ON DELETE` behavior, explicitly
    declared rather than left to database defaults
- Migration `0002_latest_observations_view.py` — hand-written, raw SQL for
  CREATE VIEW / DROP VIEW

**Depends on:** Phase 5.

**Verify:** `alembic upgrade head` succeeds on a fresh `macrodb` database.
`psql -c '\dt'` shows all 19 tables. `psql -c '\dv'` shows the
`latest_observations` view. `alembic downgrade base && alembic upgrade head`
round-trips cleanly.

**Effort:** 1 day (most of which is reviewing the autogenerate output).

---

## Phase 7 — Pydantic schemas

**Deliverables:**

- `src/macro_foundry/schemas/` with one file per domain
- For each table: `XBase`, `XCreate`, `XUpdate`, `XRead` (and `XReadDetail`
  where relevant)
- Cross-field validators on `XCreate` schemas mirror DB CHECK constraints
- All Read schemas have `model_config = ConfigDict(from_attributes=True)`

**Depends on:** Phases 4 (enums shared with schemas) and 5 (models being
schema-d).

**Verify:** `uv run python -c "from macro_foundry.schemas import SeriesCreate;
SeriesCreate(...)"` works for a valid payload. Invalid payloads raise
`ValidationError`.

**Effort:** 1-2 days. Largely mechanical but the cross-field validators
need care.

---

## Phase 8 — Seed data + CLI

**Deliverables:**

- `src/macro_foundry/seed/data/geographies.py` with COUNTRIES (all ISO 3166-1),
  SUBNATIONALS (US states at minimum), curated SUBNATIONAL_REGIONS where the
  project chooses to support them, BLOCS (G7, G20, OECD, EMU, EU, EFTA, BRICS,
  ASEAN, MERCOSUR, World)
- `src/macro_foundry/seed/data/tags.py` with the 7 fixed categories
- `src/macro_foundry/seed/data/memberships.py` with curated geography-group
  mappings (bloc → member, plus subnational_region → subnational where modeled)
- `src/macro_foundry/seed/runners/` with idempotent `ON CONFLICT DO UPDATE` logic
- `src/macro_foundry/seed/run.py` orchestrator (dependency-ordered)
- `src/macro_foundry/cli.py` with `macrodb seed [--only X] [--dry-run] [--reset]`
- `pyproject.toml` exposes `macrodb` as a script entry point

**Depends on:** Phase 7 (uses schemas to validate seed data on the way in;
optional but recommended) and Phase 6 (schema must exist to seed into).

**Verify:** `uv run macrodb seed` on a fresh DB succeeds. Re-running it produces
no errors, no duplicates. Edit a name in `data/geographies.py`, re-run, confirm
the row is updated.

**Effort:** 1 day. Most of the time is curating the geography data.

---

## Phase 9 — CRUD generator + simple routes

**Deliverables:**

- `src/macro_foundry/backend/crud.py` — the ~150-line `crud_router(model,
create_schema, update_schema, read_schema, ...)` factory
- `src/macro_foundry/backend/deps.py` — `get_session` re-export, `verify_token`
  bearer auth dep
- One router file per simple table (concepts, tags, providers, provider_catalogs,
  geographies, geography_memberships, series_families, series_family_members,
  series_tags, series_sources, derived_series, derivation_inputs,
  ingestion_feeds, both run_logs, change_proposals, change_proposal_items),
  each a one-liner registration
- `src/macro_foundry/backend/main.py` mounts all routers under `/api/v1`

**Depends on:** Phase 7.

**Verify:** `uv run uvicorn macro_foundry.backend.main:app` starts. `curl
http://localhost:8000/api/v1/concepts -H "Authorization: Bearer ..."` returns
`[]` (empty list, valid pagination shape). `POST /api/v1/concepts` with a body
creates a concept and returns it. `PATCH /api/v1/concepts/{id}` updates.
`DELETE /api/v1/concepts/{id}` deletes.

**Effort:** 2 days. Most time on the generator; routers are one-liners.

---

## Phase 10 — Hand-tuned routes

**Deliverables:**

- `src/macro_foundry/backend/api/series.py` — POST/PATCH with cross-field
  validation, dedup against existing codes, GET/{id} with eager-loaded geography
  - tags
- `src/macro_foundry/backend/api/observations.py` — POST `/observations/bulk`
  accepting a list with vintage handling, GET with filtering

**Depends on:** Phase 9.

**Verify:** Hand-tuned routes pass integration tests covering the special cases
(growth requires horizon, bulk insert with mixed valid/invalid rows, vintage
conflict resolution).

**Effort:** 1-2 days.

---

## Phase 11 — SQLAdmin

**Deliverables:**

- `src/macro_foundry/backend/admin/_base.py` — `BaseModelView` with project
  defaults
- `src/macro_foundry/backend/admin/auth.py` — `BasicAuthBackend`
- `src/macro_foundry/backend/admin/views/` — one file per domain, ~10-20 lines
  per concrete view (column_list, column_searchable_list, column_filters, FK
  formatters, JSONB widget overrides where needed)
- `src/macro_foundry/backend/admin/register.py` — registers all views
- `src/macro_foundry/backend/main.py` mounts the Admin under `/admin`

**Depends on:** Phase 5 (models).

**Verify:** Open `http://localhost:8000/admin`, log in with admin credentials
from `.env.local`. Each table is browsable. Creating a concept through the UI
works and persists. FKs show meaningful labels, not UUIDs.

**Effort:** 1-2 days.

---

## Phase 12 — Tests

**Deliverables:**

- `tests/conftest.py` — async fixtures: session-scoped `test_engine` (sets up
  `macrodb_test`, runs migrations, runs seeds); per-test `session` with
  SAVEPOINT rollback; `client` httpx.AsyncClient with `get_session` override
- `tests/test_migrations.py` — Alembic round-trip test
- `tests/test_seed.py` — three seed idempotency tests
- `tests/test_crud_generator.py` — eight tests against `concepts` covering
  list/get/create/update/delete + filters
- `tests/test_constraints.py` — ten tests covering the key UNIQUE/CHECK/FK
  constraints
- `tests/test_series_routes.py` — five hand-tuned series tests
- `tests/test_observations_routes.py` — bulk insert tests
- `tests/test_admin_auth.py` — auth on the admin
- `tests/test_e2e.py` — one end-to-end smoke test

**Depends on:** All previous phases.

**Verify:** `uv run pytest` exits 0. All ~28 tests pass. Total runtime under 30s.

**Effort:** 2-3 days. Tests are real work, not boilerplate.

---

## Phase 13 — Neon parity verification

**Deliverables:**

- A Neon project created (PG 18 default)
- Both roles set up on Neon (the project owner serves as `macrodb_owner`
  equivalent; `macrodb_app` created via SQL on first connect)
- `MACRODB_OWNER_URL` and `MACRODB_APP_URL` updated locally to point at Neon's
  direct endpoint
- `alembic upgrade head` succeeds against Neon
- `uv run macrodb seed` succeeds against Neon
- `uv run pytest` succeeds (or a documented subset, if any tests are intentionally
  local-only)
- `/admin` and `/docs` work against the API pointed at Neon
- Local config restored after the test

**Depends on:** All previous phases.

**Verify:** Everything above completes without code changes between local and
Neon. Any divergences are documented in `progress_tracker.md` and addressed
before declaring the phase complete.

**Effort:** Half-day to a day, depending on Neon setup speed.

---

## What's not on this plan

These are deliberately not phases, despite being important:

- **Ingestion fetchers** (FRED, World Bank, Alpha Vantage, IMF) — next phase
  after this one.
- **The AI agent (LangGraph)** — multi-phase later.
- **Frontend** — when the data layer is mature enough.
- **Series composition trees** (`series_composition_nodes`) — design exists,
  build later.
- **Materialized views, dbt for derivations, custom auth, multi-tenant features**
  — flagged in `architecture.md` as future directions; not now.

If a request lands that doesn't fit one of these 13 phases, **ask the user**
whether it belongs in this phase, the next one, or further out. Do not silently
scope-creep.
