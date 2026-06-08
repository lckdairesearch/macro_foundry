# Progress Tracker

This file is the living record of what's been done. Update it when a phase
completes, when something deviates from the build plan, or when a handoff
between sessions happens.

Format per entry: `[YYYY-MM-DD] Phase N — Status. Notes.`

Most recent at the top.

---

## Current phase

**Phase 13 — Neon parity verification** (next up).

Phase 12 is now complete. The local test harness now seeds `macrodb_test` once
per session, isolates each test with transaction rollback, and covers the
migration chain, seed idempotency, CRUD generator, constraint surface,
hand-written routes, admin auth, and one end-to-end API smoke before the final
Neon parity pass.

## Phase status

| Phase | Title                          | Status      |
| ----- | ------------------------------ | ----------- |
| 0     | Agent infrastructure           | ✅ Complete |
| 1     | Repo bootstrap                 | ✅ Complete |
| 2     | Docker + Postgres + roles      | ✅ Complete |
| 3     | Config + session + base        | ✅ Complete |
| 4     | Enums                          | ✅ Complete |
| 5     | Models                         | ✅ Complete |
| 6     | Alembic + initial migrations   | ✅ Complete |
| 7     | Pydantic schemas               | ✅ Complete |
| 8     | Seed data + CLI                | ✅ Complete |
| 9     | CRUD generator + simple routes | ✅ Complete |
| 10    | Hand-tuned routes              | ✅ Complete |
| 11    | SQLAdmin                       | ✅ Complete |
| 12    | Tests                          | ✅ Complete |
| 13    | Neon parity verification       | ⏳          |

## Log

### [2026-06-08] Phase 12 — Complete

Phase 12 is now closed. The test harness and suite were expanded to match the
build-plan coverage:

- rewired `tests/conftest.py` so the session-scoped setup migrates and seeds
  `macrodb_test` once, while each individual test runs inside a rolled-back
  transaction boundary instead of truncating the database
- added the missing Phase 12 modules:
  `tests/test_migrations.py`, `tests/test_seed.py`,
  `tests/test_crud_generator.py`, `tests/test_constraints.py`,
  `tests/test_admin_auth.py`, and `tests/test_e2e.py`
- kept the existing series / observations / admin coverage green against the
  seeded baseline by making the route tests seed-aware and narrowing the admin
  auth assertions to the behaviors that matter

Verification:

- `uv run ruff check tests` exited 0
- `uv run pytest -q` exited 0 with `68 passed in 2.22s`

### [2026-06-08] Phase 8 — Complete

Phase 8 is now closed. The seed/CLI work is complete and the final verification
step was satisfied by running the seed command against the local database.

Completion notes:

- the curated seed data surface remains the same as previously documented:
  geographies, memberships, tags, default providers, and provider catalogs
- the dependency-ordered seed runners and CLI entrypoint remain in place with
  idempotent upsert behavior
- this resolves the last unfinished earlier phase after Phases 9-11 were
  completed out of order

Verification:

- per user confirmation on 2026-06-08, the project seed command was run
  successfully against the local database, so the Phase 8 verify step is now
  satisfied


### [2026-06-08] SQLAdmin hardening — filters + tab coverage + navigation cleanup

The SQLAdmin surface was hardened after the first real browser pass exposed a
runtime break in list-page filters:

- fixed the shared admin base so raw `column_filters` declarations are
  normalized into concrete SQLAdmin filter objects, which restores enum,
  boolean, date, and numeric filtering across the admin list pages
- added `tests/test_admin_auth.py` coverage for the full mounted admin surface,
  logging in and asserting that every registered `/admin/<identity>/list`
  route renders successfully against `macrodb_test`
- reorganized the admin sidebar around the domain layers already described in
  the project docs (`Core Curation`, `Provider Layer`, `Series Catalog`,
  `Observation Layer`, `Governance`) instead of leaving 19 flat tabs in one
  undifferentiated list
- added sensible default list ordering for operator-facing pages so catalog
  tables open alphabetically and log / observation / governance views open
  newest-first

Verification:

- `uv run ruff check src/macro_foundry/backend/admin tests/test_admin_auth.py`
  exited 0
- `uv run pytest tests/test_admin_auth.py -q` exited 0 with `20 passed`

### [2026-06-08] Environment naming — local dev/test + cloud prod

Clarified and partially implemented the physical database naming model without
changing the logical `macrodb` system name:

- local Docker now uses `macrodb_dev` for the working database and
  `macrodb_test` for the isolated test database
- cloud / Neon is documented as production-only for now, using one physical
  database named `macrodb_prod`
- the existing `MACRODB_OWNER_URL`, `MACRODB_APP_URL`, and `MACRODB_TEST_URL`
  config surface remains unchanged; only the physical DB names behind those URLs
  changed
- `.env.example`, local bootstrap defaults, and the local `.env.local` on this
  machine were updated to point at `macrodb_dev` instead of `macrodb`
- because the local Postgres named volume preserves physical databases, existing
  local users need a full local DB reset / volume recreation rather than a
  plain container restart to pick up the renamed local databases
- local Docker commands must use `docker compose --env-file .env.local ...`
  unless a real `.env` file is added, because Compose does not read `.env.local`
  automatically and will otherwise fall back to placeholder passwords

Follow-on documentation work:

- ADR 0009 records the environment-specific physical database naming decision
- ADR 0006 remains the source of truth for the two-role split itself; the new
  ADR supersedes only the older physical database naming examples

### [2026-06-08] Phase 10 — Complete (implemented out of order)

The hand-written API surface now covers the two Phase 10 hotspots:

- added `src/macro_foundry/backend/api/series.py` with explicit create/update
  handling for canonical series, including merged-state revalidation on PATCH,
  proactive duplicate-code detection, and a detail GET route that eager-loads
  geography plus attached tags
- added `src/macro_foundry/backend/api/observations.py` with filtered list
  reads plus `POST /observations/bulk`, which validates each row individually,
  rejects duplicate keys within a single request, checks referenced IDs before
  writing, and upserts on `(series_id, period_start, vintage_date)` conflicts
- extended the schema surface with `SeriesReadDetail`, observation-bulk result
  models, and router registration so the new endpoints are mounted under
  `/api/v1`
- added focused route coverage in `tests/conftest.py`,
  `tests/test_series_routes.py`, and `tests/test_observations_routes.py` using
  the real `macrodb_test` database with Alembic migrations applied

Deviation note:

- completed Phase 10 before finishing Phase 8 because the user asked to
  implement the hand-tuned routes directly; seed/CLI work remains in progress

Verification:

- `.uv-bootstrap/bin/uv run ruff check src/macro_foundry/backend/api/series.py
  src/macro_foundry/backend/api/observations.py src/macro_foundry/schemas/series.py
  src/macro_foundry/schemas/observation.py src/macro_foundry/schemas/__init__.py
  tests/conftest.py tests/test_series_routes.py tests/test_observations_routes.py`
  exited 0
- `.uv-bootstrap/bin/uv run pytest tests/test_series_routes.py
  tests/test_observations_routes.py` exited 0 with `8 passed`

### [2026-06-08] Phase 11 — Complete (implemented out of order)

SQLAdmin now exists as a mounted admin surface ahead of Phases 8-10 because its
documented dependency is only the Phase 5 model graph:

- added `src/macro_foundry/backend/admin/_base.py` with shared `BaseModelView`
  defaults, relationship-label helpers, and an admin-specific form converter so
  foreign-key selects render meaningful labels instead of model reprs
- added `src/macro_foundry/backend/admin/auth.py` with a single-user
  `BasicAuthBackend` wired to the existing `settings.admin.*` credentials and
  session secret
- added domain view modules under `src/macro_foundry/backend/admin/views/`
  covering all 19 V3 tables, including project-default form exclusions,
  relationship formatters, JSONB textarea widget overrides, and read-only admin
  treatment for append-only observations and run logs
- added `src/macro_foundry/backend/admin/register.py` and mounted SQLAdmin at
  `/admin` from `src/macro_foundry/backend/main.py`

Deviation note:

- completed Phase 11 before Phase 10 because the user asked to implement the
  admin surface directly, and Phase 11 depends only on the Phase 5 model graph

Verification:

- `.venv/bin/ruff check src/macro_foundry/backend/admin
  src/macro_foundry/backend/main.py` exited 0
- `.venv/bin/python -c "from macro_foundry.backend.main import app, admin;
  print('routes=', len(app.routes)); print('admin=', type(admin).__name__)"`
  printed `routes= 91` and `admin= Admin`
- an unsandboxed FastAPI `TestClient` smoke script loaded `/admin/login`,
  authenticated with the configured admin credentials, created a concept
  through `/admin/concept/create`, verified the row in Postgres, deleted the
  temporary concept, and printed `admin-smoke-ok`
- an unsandboxed follow-up smoke script inserted two temporary geographies,
  loaded `/admin/geography-membership/create`, confirmed the foreign-key select
  rendered a human-readable `CODE - Name` label, cleaned up the temporary rows,
  and printed `admin-fk-label-ok ...`

### [2026-06-08] Phase 9 — Complete (out of order ahead of Phase 8)

FastAPI entrypoint scaffolding and the thin CRUD layer now exist for the simple
tables:

- added `src/macro_foundry/backend/crud.py` with one generator covering list,
  get, create, patch, and delete routes
- added `src/macro_foundry/backend/deps.py` with bearer-token auth and the
  shared session dependency surface
- added one router module per simple table under `src/macro_foundry/backend/api/`
  and registered them centrally for `/api/v1`
- added `src/macro_foundry/backend/main.py` with the FastAPI app entrypoint and
  a minimal `/healthz` route
- taught the generator to handle simple equality filters and composite-key
  junction tables so `series_family_members` and `series_tags` do not need a
  separate routing pattern
- added `uvicorn` to the runtime dependencies so the documented app startup
  command is actually available

Deviation note:

- completed Phase 9 before Phase 8 because the user asked to start API work
  immediately; the seed data and CLI work remains in progress

Verification:

- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run ruff check src/macro_foundry/backend`
  exited 0
- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run python -c "from macro_foundry.backend.main import app; print(len(app.routes))"`
  printed `90`
- a live ASGI-backed smoke script against the local Postgres database completed
  list/create/filter/patch/delete on `/api/v1/concepts/` and printed
  `crud-smoke-ok`
- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run uvicorn macro_foundry.backend.main:app --host 127.0.0.1 --port 8001`
  started successfully, and `curl http://127.0.0.1:8001/healthz` returned
  `{"status":"ok"}`

### [2026-06-08] Phase 8 — Scope finalized before verification

Phase 8 implementation reached the point where the remaining step was only the
final seed-command verification. The scope clarifications captured in code and
docs were:

- expanded the seed scope beyond the original geography/tag baseline to include
  a curated default provider and provider-catalog seed set
- fixed the geography curation boundary to all ISO 3166-1 geographies, US
  states plus DC, Japan prefectures, and the 8 Japan `chiho` regions
- fixed the tag taxonomy to the normalized 7-category subject set used in
  `src/macro_foundry/seed/data/tags.py`
- fixed the provider naming convention for country-scoped official sources to
  use 3-letter geography prefixes in the canonical provider name (`USA FRED`,
  `HKG Census and Statistics Department`, `JPN e-Stat`)
- fixed the default membership policy to current memberships by default, with
  explicit historical EU change tracking for the last 20 years including Brexit
- added the explicit `AU` geography exception so the seeded G20 membership can
  match the current official composition
- deferred two follow-up items to a later V2-style pass rather than changing
  V3 mid-phase: a nullable provider→geography link and a scheduled checker for
  EU membership expansion/retraction drift

Verification at that checkpoint:

- `uv run python - <<'PY' ...` imported the Phase 8 seed data modules and
  printed the expected counts for countries, subnationals, memberships,
  providers, catalogs, and tags
- `uv run pytest -q tests/test_seed_data.py tests/test_schemas.py`
  exited 0 with `15 passed`

### [2026-06-08] Phase 7 — Complete

Pydantic schemas now cover the full V3 table surface:

- added `src/macro_foundry/schemas/` modules for concepts, geographies, tags,
  providers, series, observations, derived-series metadata, ingestion feeds,
  run logs, and governance
- implemented `Base` / `Create` / `Update` / `Read` variants for each table,
  plus detail read models where same-domain nested rows are useful
- added schema-side validators mirroring the Phase 5 cross-field constraints:
  subnational parent requirement, growth-series horizon requirement,
  currency-series currency-code requirement, and observation period bounds
- exported the public schema surface from `src/macro_foundry/schemas/__init__.py`
- added focused Phase 7 coverage in `tests/test_schemas.py`

Verification:

- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run ruff check src/macro_foundry/schemas tests/test_schemas.py`
  exited 0
- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run pytest tests/test_schemas.py`
  exited 0 with `7 passed`
- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run python -c "... from macro_foundry.schemas import SeriesCreate ..."`
  printed `schemas-ok`

### [2026-06-08] Phase 6 — Complete

Alembic scaffolding and the initial migration chain now exist and verify cleanly:

- added `alembic.ini`, `alembic/env.py`, and `alembic/script.py.mako`, with
  Alembic bound to `MACRODB_OWNER_URL` rather than the app role
- generated and reviewed `alembic/versions/0001_initial_schema.py` from
  `Base.metadata`, covering all 19 V3 tables with named UNIQUE constraints,
  cross-column CHECK constraints, enum CHECK constraints, and explicit
  ADR-0008-aligned `ondelete` behavior
- added handwritten migration `alembic/versions/0002_latest_observations_view.py`
  to create and drop the `latest_observations` view via raw SQL
- corrected the shared enum helper during migration review so enum columns now
  persist enum values rather than member names, and emit real DB CHECK
  constraints via `create_constraint=True`

Verification:

- `.venv/bin/ruff check alembic src/macro_foundry/models/_schema_policy.py`
  exited 0
- `.venv/bin/python -c ...` confirmed `tables=19`, `Series.frequency` stores
  `['D', 'W', 'M', 'Q', 'S', 'A']`, and the enum type has
  `create_constraint=True`
- `.venv/bin/alembic upgrade head` succeeded against the local owner database
- `.venv/bin/alembic downgrade base && .venv/bin/alembic upgrade head`
  round-tripped cleanly
- a verification query after the round-trip confirmed 19 domain tables plus the
  `latest_observations` view in `public`

### [2026-06-08] Schema policy refactor — complete before Phase 6

Deepened the ORM graph's shared schema policy without starting Alembic work:

- added a private helper module at `src/macro_foundry/models/_schema_policy.py`
  with the two agreed seams only: `enum_column(...)` and `fk_uuid(...)`
- updated `docs/code_standards.md` to anchor the allowed helper boundary in
  writing before the refactor
- applied the seam across the repeated enum and non-PK UUID foreign-key shapes
  in the Phase 5 model graph
- kept composite-key junction structure local in model modules; the
  `series_tags` and `series_family_members` FK columns remain inline because
  `primary_key=True` is part of the local table structure rather than shared FK
  policy
- did not add relationship, CHECK, UNIQUE, scalar-column, or PK helpers

Verification:

- `.uv-bootstrap/bin/uv run ruff check src/macro_foundry/models` exited 0
- `.uv-bootstrap/bin/uv run python -c "from macro_foundry.models import *;
  print('imports-ok')"` printed `imports-ok`
- `.uv-bootstrap/bin/uv run python -c "from macro_foundry.models import *; from
  sqlalchemy.orm import configure_mappers; configure_mappers(); from
  macro_foundry.db.base import Base; print(f'tables={len(Base.metadata.tables)}')"`
  printed `tables=19`

### [2026-06-08] Documentation alignment — `CONTEXT.md` moved to repo root

Aligned markdown docs with the glossary move from `docs/CONTEXT.md` /
`docs/glossary.md` to the repo-root `CONTEXT.md`:

- updated `AGENTS.md` and `CLAUDE.md` so the required reading list and
  documentation-update rules point at `CONTEXT.md`
- updated `docs/architecture.md` and `docs/build_plan.md` so the documented repo
  layout matches the current file location
- updated `README.md` to list `CONTEXT.md` as a first-class project entrypoint

### [2026-06-08] Phase 5 — Complete

SQLAlchemy models now cover the full V3 schema surface:

- added model modules for geography, concepts, tags, providers, series,
  observations, derived-series metadata, ingestion feeds, run logs, and
  governance
- implemented the V3 cross-column CHECK constraints and the three one-to-one
  UNIQUE constraints called out in the build plan
- wired every foreign key with explicit ADR-0008-aligned `ondelete` behavior
  and exported the full model graph from `src/macro_foundry/models/__init__.py`
- kept `series_tags` and `series_family_members` schema-native instead of
  forcing synthetic IDs, because V3 defines them as composite-key tables
- corrected stale docs that said V3 had 18 tables; the canonical schema
  currently defines 19

Verification:

- `.uv-bootstrap/bin/uv run ruff check src/macro_foundry/models` exited 0
- `.uv-bootstrap/bin/uv run python -c "from macro_foundry.models import *; from
  macro_foundry.db.base import Base; print(len(Base.metadata.tables))"` printed
  `19`
- `.uv-bootstrap/bin/uv run python -c "from macro_foundry.models import *; from
  sqlalchemy.orm import configure_mappers; configure_mappers(); print('mappers-ok')"`
  printed `mappers-ok`

### [2026-06-08] Foreign-key deletion policy — ADR 0008

Resolved an ambiguity that blocked Phase 5 models and Phase 6 migration review:

- added ADR 0008 defining explicit `ON DELETE` behavior for every V3 foreign key
- updated the canonical schema relationships section so each FK now carries its
  delete policy inline
- updated the architecture and build plan so Phase 5/6 no longer assume an
  unstated deletion policy

### [2026-06-08] Phase 4 correction — removed mistaken tag enum placeholder

Corrected a Phase 4 artifact that contradicted ADR 0002:

- removed `src/macro_foundry/enums/tag.py`; it was an empty placeholder with no
  runtime callers
- updated the architecture and build plan so the enum package only covers
  code-routing and CHECK-constrained values
- made the tags exception explicit in current progress notes: tags are curated
  seed data, not Python enums

### [2026-06-08] Ingestion feed taxonomy — `file_upload` renamed to `file`

Refined `FeedMethod` so the enum describes acquisition mechanism rather than
operator workflow:

- renamed `file_upload` to `file` to cover uploads, watched paths, and other
  file-based ingestion paths
- added `scrape` as a distinct future ingestion method alongside `api` and
  `file`
- updated the glossary and canonical schema comments to match the broader
  ingestion-method vocabulary

### [2026-06-08] Geography taxonomy — Added `subnational_region`

Recorded a new ADR and updated the domain language for country-scoped grouping
geographies:

- added ADR 0007 defining `subnational_region` as a first-class geography type
  for country-scoped groupings such as Japan `chiho` and US `Midwest`
- clarified that `parent_geography_id` is the country anchor for both
  `subnational` and `subnational_region`
- clarified that subnational membership into subnational regions is modeled via
  `geography_memberships`, not a forced single tree
- updated the schema/build-plan references that previously treated
  `parent_geography_id` as subnational-only

### [2026-06-08] Phase 4 — Complete

Enum scaffolding landed for the full V3 schema surface:

- added domain enum modules under `src/macro_foundry/enums/` for geography,
  series, providers, derivations, run logs, and governance workflows
- re-exported the public enum surface from `src/macro_foundry/enums/__init__.py`
  so models and schemas can import from one stable package entrypoint
- kept tags out of the enum package because they are curated seed data rather
  than code-routing enums

Verification:

- `.uv-bootstrap/bin/uv run ruff check src/macro_foundry/enums` exited 0
- `.uv-bootstrap/bin/uv run python -c "from macro_foundry.enums import Frequency;
print(Frequency.MONTHLY.value)"` printed `M`

### [2026-06-08] Agent manual — Commit message guidance added

Updated `AGENTS.md` and `CLAUDE.md` with a shared commit-message standard:

- use a short `type(scope): subject` format when it improves clarity
- write for a developer who understands the domain but has not read the diff
- explain behavioral, schema, or architectural impact rather than listing files
- avoid vague subjects and patch-summary bodies

### [2026-06-08] Phase 3 — Complete

Core runtime scaffolding landed:

- added `src/macro_foundry/config.py` with a typed `Settings` object that reads
  `.env.local`, exposes `settings.db`, `settings.admin`, and `settings.api`,
  and configures the project logger
- added `src/macro_foundry/db/base.py` with the shared declarative `Base`,
  `TimestampedBase`, and `CreatedAtBase` mixins using server-side `uuidv7()`
  and timestamp defaults
- added `src/macro_foundry/db/session.py` with the async engine, async
  sessionmaker, and request-scoped `get_session()` dependency using the agreed
  Neon-safe pool settings and `expire_on_commit=False`
- updated `src/macro_foundry/db/__init__.py` exports to expose the shared DB
  primitives cleanly
- expanded `.env.example` with the API/admin/logging placeholders used by the
  new settings module
- populated the local gitignored `.env.local` from the example so Phase 3 can
  be verified end-to-end on this machine

Verification:

- `.uv-bootstrap/bin/uv run ruff check src/macro_foundry/config.py src/macro_foundry/db`
  exited 0
- `.uv-bootstrap/bin/uv run python ...` using `macro_foundry.db.session.async_engine`
  executed `SELECT 1` successfully against the local database

### [2026-06-08] Phase 2 — Complete

Docker and local Postgres bootstrap landed:

- added `docker-compose.yml` for a local `postgres:18.4` service with a
  persistent named volume, port 5432, and a healthcheck
- added `docker/postgres/init/01_roles.sql` to create `macrodb_owner` and
  `macrodb_app`, create `macrodb` and `macrodb_test`, and apply app-role grants
  plus default privileges in both DBs
- updated `.env.example` with `POSTGRES_PASSWORD` alongside the Phase 2 DB URLs

Verification:

- `docker compose config` exited 0
- `docker compose up -d --force-recreate` started a healthy Postgres 18.4
  container
- container logs confirmed `01_roles.sql` ran successfully on init
- role checks inside the container confirmed `macrodb_owner` and `macrodb_app`
  exist
- connection checks confirmed `macrodb_owner` can connect to `macrodb`,
  `macrodb_app` can connect to both `macrodb` and `macrodb_test`
- privilege boundary check confirmed `macrodb_app` cannot create tables in
  `public`

Deviation note:

- this host does not have `psql` installed on `PATH`, so verification used
  `docker compose exec ... psql ...` inside the running container
- Postgres 18 images expect the named volume mounted at `/var/lib/postgresql`,
  not `/var/lib/postgresql/data`; the compose file reflects that requirement

### [2026-06-08] Phase 1 — Complete

Repo skeleton aligned to `docs/architecture.md`:

- created `docs/`, `docs/adr/`, `docs/schema/`, `src/macro_foundry/`, `alembic/`,
  `docker/`, `tests/`, and `scripts/` scaffolding
- moved project docs under `docs/`
- moved ADRs under `docs/adr/`
- moved the canonical V3 schema to `docs/schema/db_er.txt`
- replaced the root `README.md` with a repo entrypoint and moved the ADR index
  content to `docs/adr/README.md`
- added `.gitignore`, `.env.example`, and a gitignored `.env.local`
- added `pyproject.toml` with the Phase 1 runtime and dev dependencies
- corrected the glossary-path references in `architecture.md` and
  `build_plan.md` to match the then-current repo layout
- generated `uv.lock` and the project `.venv`

Verification:

- `.uv-bootstrap/bin/uv sync` exited 0
- `.uv-bootstrap/bin/uv run python -c "import macro_foundry"` exited 0

Deviation note:

- this host did not have `uv` installed on `PATH`, so verification used a
  repo-local bootstrap venv at `.uv-bootstrap/` to provide the `uv` binary

### [2026-06-08] Phase 0 — Complete

Agent infrastructure laid down:

- `CLAUDE.md` and `AGENTS.md` at project root (identical content)
- `CONTEXT.md`, `docs/project_overview.md`, `docs/architecture.md`,
  `docs/code_standards.md`, `docs/build_plan.md`, `docs/progress_tracker.md`
- `docs/adr/0001-uuidv7-server-side-defaults.md` through
  `docs/adr/0006-two-role-architecture.md`

Pocock skills installed:

- `/grill-with-docs`
- `/tdd`
- `/diagnose`
- `/zoom-out`

V3 schema confirmed final at `docs/schema/db_er.txt`. Two enforcements
intentionally omitted (no `reference_kind → reference_year` CHECK, no
`series_family_members` partial unique). These are documented in `build_plan.md`
Phase 5 so they aren't silently re-added.

Decisions ratified in this session:

1. uuidv7 + timestamp defaults — server-side
2. CHECK constraints via Python enums (not native PG ENUM)
3. Thin in-repo CRUD generator + hand-tuned hotspots (not PostgREST, not Django,
   not SQLModel)
4. psycopg3 async (not asyncpg)
5. Seed via Typer CLI with `ON CONFLICT DO UPDATE` (not Alembic data migrations)
6. SQLAdmin with `BaseModelView` defaults + per-table overrides
7. ~28-test suite focused on generator + constraints + integration
8. Single bearer token API auth + basic-auth admin
9. Direct Neon endpoint (not pooled `-pooler`) with `pool_pre_ping` + `pool_recycle`
10. Hand-written Alembic migration for `latest_observations` view
11. Two-role split: `macrodb_owner` for migrations, `macrodb_app` for everything else

### [Future entries go above this line]
