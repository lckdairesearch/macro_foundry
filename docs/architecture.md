# Architecture

This document captures the decided architecture of `macro_foundry`. It is the source
of truth for how the system is structured and why. Do not deviate without writing
a new ADR and updating this file.

## Stack

- **Language:** Python 3.12+
- **Package manager:** `uv` (workspace not used; single package layout)
- **Database:** Postgres 18.4 locally via Docker; Neon (PG 18 default) for cloud
- **ORM / async driver:** SQLAlchemy 2.x async + psycopg3 (`postgresql+psycopg://`)
- **Migrations:** Alembic
- **Validation:** Pydantic v2 + pydantic-settings
- **API framework:** FastAPI (async)
- **Admin:** SQLAdmin (mounted at `/admin`)
- **CLI:** Typer
- **Tests:** pytest + pytest-asyncio + httpx.AsyncClient
- **Future (not this phase):** Next.js + Tremor frontend; LangGraph for the AI
  agent; an external scheduler (GitHub Actions / APScheduler) for ingestion.

## Why this stack — short summary of rejected alternatives

Each was considered explicitly and rejected. ADRs cover the reasoning.

- **PostgREST / Supabase / Hasura** — wrong validation philosophy for a curated
  layer; writes need to go through Python where structured rules and the future
  agent can share logic.
- **Django + DRF** — better admin, but SQLAlchemy 2.x beats Django ORM for the
  query patterns we need (CTEs, window functions, DISTINCT ON for the view).
- **SQLModel** — async support rougher than raw SQLAlchemy; doesn't save much
  once Create/Update/Read variants are required.
- **TimescaleDB** — Neon supports it now, but vanilla PG is sufficient at this
  scale and avoids tying us to one extension.
- **asyncpg** — faster than psycopg3 (~20-30% in tight loops) but requires
  `statement_cache_size=0` under PgBouncer and forces a different driver from
  sync code. Unified driver wins.
- **Native PG ENUM types** — rigid migrations; CHECK constraints over Python
  enums are more evolvable.

## High-level layering

```
┌─────────────────────────────────────────────────────────┐
│  FastAPI routes + SQLAdmin              (entry layer)   │
│  - thin CRUD generator for simple tables                 │
│  - hand-tuned routes for series, observations            │
│  - basic auth for admin; bearer token for API           │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│  Pydantic schemas                       (validation)    │
│  - Base / Create / Update / Read variants                │
│  - cross-field validators mirror DB CHECKs               │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│  SQLAlchemy async models                (data model)    │
│  - V3 schema, 19 tables                                  │
│  - mixin pattern for id/timestamps, with                 │
│    schema-native composite-PK junction exceptions        │
│  - CHECK constraints via Enum(native_enum=False)         │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│  Postgres 18.4                           (storage)      │
│  - uuidv7() native, server-side default                  │
│  - two roles: macrodb_owner, macrodb_app                 │
│  - latest_observations view                              │
└─────────────────────────────────────────────────────────┘
```

Reads and writes both go through FastAPI. There is no second front door (no
PostgREST, no direct DB access for clients). SQLAdmin connects as the same
`macrodb_app` role as the API.

## Directory layout

```
macro_foundry/
├── CLAUDE.md                       # agent entry (Claude Code)
├── AGENTS.md                       # agent entry (Codex, identical to CLAUDE.md)
├── CONTEXT.md                      # domain glossary / canonical terminology
├── .env.local                      # secrets, gitignored
├── .env.example                    # template, committed
├── pyproject.toml                  # uv-managed
├── uv.lock
├── alembic.ini
├── docker-compose.yml              # single PG18 container, two DBs inside
│
├── docker/
│   └── postgres/
│       └── init/
│           └── 01_roles.sql        # creates macrodb_owner, macrodb_app on first boot
│
├── alembic/
│   ├── env.py                      # connects via MACRODB_OWNER_URL
│   └── versions/
│
├── src/macro_foundry/
│   ├── __init__.py
│   ├── config.py                   # pydantic-settings, reads .env.local
│   ├── cli.py                      # Typer entry point (macrodb command)
│   │
│   ├── db/
│   │   ├── base.py                 # declarative Base + TimestampedBase + CreatedAtBase
│   │   └── session.py              # async engine, AsyncSessionLocal, get_session()
│   │
│   ├── enums/                      # Python str-Enum classes for code-routing and CHECK-constrained values
│   │   ├── __init__.py
│   │   ├── geography.py
│   │   ├── series.py
│   │   ├── provider.py
│   │   ├── derivation.py
│   │   ├── run.py
│   │   ├── governance.py
│   │
│   ├── models/                     # SQLAlchemy ORM — V3 tables
│   │   ├── __init__.py             # exports all models so Alembic sees metadata
│   │   ├── geography.py
│   │   ├── concept.py
│   │   ├── tag.py
│   │   ├── provider.py
│   │   ├── series.py
│   │   ├── observation.py
│   │   ├── derived.py
│   │   ├── ingestion.py
│   │   ├── run_log.py
│   │   └── governance.py
│   │
│   ├── schemas/                    # Pydantic Base/Create/Update/Read per table
│   │   ├── __init__.py
│   │   ├── _base.py                # shared mixins
│   │   ├── geography.py
│   │   ├── concept.py
│   │   ├── tag.py
│   │   ├── provider.py
│   │   ├── series.py
│   │   ├── observation.py
│   │   ├── derived.py
│   │   ├── ingestion.py
│   │   ├── run_log.py
│   │   └── governance.py
│   │
│   ├── seed/                       # idempotent seed data
│   │   ├── data/                   # typed Python data (COUNTRIES, BLOCS, TAGS, PROVIDERS, PROVIDER_CATALOGS, MEMBERSHIPS)
│   │   ├── runners/                # async upsert / natural-key reconciliation logic
│   │   └── run.py                  # orchestrator, dependency order
│   │
│   ├── ingestion/                  # scaffold only this phase; HTTP clients later
│   │   ├── __init__.py
│   │   ├── providers/              # one module per provider (empty for now)
│   │   ├── transforms/
│   │   └── runners/
│   │
│   └── backend/
│       ├── main.py                 # FastAPI app, mounts api + admin
│       ├── crud.py                 # ~150-line thin CRUD generator
│       ├── deps.py                 # get_session, verify_token
│       ├── api/                    # one router per table; simple ones use crud_router
│       │   ├── concepts.py
│       │   ├── tags.py
│       │   ├── providers.py
│       │   ├── series.py           # hand-written
│       │   ├── observations.py     # hand-written
│       │   └── ... (one per table)
│       └── admin/
│           ├── _base.py            # BaseModelView
│           ├── auth.py             # BasicAuthBackend
│           ├── register.py         # registers all views
│           └── views/              # one view per domain (geography, series, etc.)
│
├── tests/
│   ├── conftest.py                 # async fixtures: test_engine, session, client
│   ├── test_migrations.py
│   ├── test_seed.py
│   ├── test_crud_generator.py
│   ├── test_constraints.py
│   ├── test_series_routes.py
│   ├── test_observations_routes.py
│   ├── test_admin_auth.py
│   └── test_e2e.py                 # full chain smoke test
│
├── scripts/                        # one-off ops scripts; not part of the package
│   ├── reset_db.sh
│   └── dump_schema.sh
│
└── docs/                           # see CLAUDE.md / AGENTS.md for the entry point
    ├── project_overview.md
    ├── architecture.md
    ├── code_standards.md
    ├── build_plan.md
    ├── progress_tracker.md
    ├── adr/
    │   └── 00XX-*.md
    └── schema/
        ├── db_er.txt               # V3 eraser.io source (canonical)
        └── db_er_diagram.svg       # rendered diagram
```

## Database roles

Two roles, both created in `docker/postgres/init/01_roles.sql` on first container boot:

- **`macrodb_owner`** — owns all schema. Used only by Alembic (`MACRODB_OWNER_URL`).
  Has full DDL on the `public` schema. Equivalent role on Neon is the project owner
  (created via Neon SQL on first setup).
- **`macrodb_app`** — used by FastAPI, SQLAdmin, ingestion (later), and tests
  (`MACRODB_APP_URL`). Has SELECT/INSERT/UPDATE/DELETE on all tables in `public`,
  plus `USAGE` on the schema. No DDL.

The split means: even if an app endpoint is compromised, it cannot ALTER tables or
DROP data. Migrations always run as a separate role with explicit credentials.

## Database connection details

- **Local:** one Postgres 18.4 container with two databases inside (`macrodb`,
  `macrodb_test`). Both roles exist in both DBs.
- **Neon:** use the **direct endpoint** (not the `-pooler` suffix). Normal SQLAlchemy
  pooling. `psycopg3` doesn't aggressively use prepared statements, so the
  PgBouncer-transaction-mode compatibility issue that affects `asyncpg` doesn't apply.
- **Engine config:** `pool_pre_ping=True`, `pool_recycle=300`, `pool_size=5`,
  `max_overflow=10`. The pre-ping and recycle are required for Neon's scale-to-zero
  behavior — connections can be killed during idle suspend.

## Async patterns — what you must know

This catches every developer new to async SQLAlchemy. Read `code_standards.md` for
the canonical rules; here are the architectural reasons:

- **`expire_on_commit=False`** is required, not optional. In sync SQLAlchemy, commit
  marks loaded objects as stale, and the next attribute access silently re-fetches.
  In async, re-fetch needs `await`, but FastAPI's response serialization happens
  after the route returns the session — accessing attributes would crash. Setting
  this to False keeps in-memory state usable.
- **No lazy loading.** All relationships must be eager-loaded explicitly with
  `selectinload` or `joinedload`. If you see `MissingGreenlet`, this is why.
- **One session per request.** The `get_session()` dependency yields a session,
  rolls back on exception, closes at the end of the request.

## CRUD generator philosophy

Most tables (~14 of 18) are pure CRUD. Writing them by hand is repetitive and
introduces drift between endpoints. We use one in-repo `crud_router(model, ...)`
factory (~150 lines) that produces standard GET-list, GET-by-id, POST, PATCH,
DELETE routes with consistent behavior.

Tables with real semantic logic (`series` with cross-field validation,
`observations` with bulk insert and vintage handling, governance lifecycle endpoints)
get hand-written routes. The generator is opt-in per table, never imposed.

This is **not a third-party CRUD library**. We don't trust their maintenance status
or their fit with SQLAlchemy 2.x async. The generator is our code, simple to read,
simple to extend.

## Enum enforcement

Single source of truth: Python `str, Enum` classes in `src/macro_foundry/enums/`,
grouped by domain. Used identically in SQLAlchemy models and Pydantic schemas:

```python
# Model
frequency: Mapped[Frequency] = mapped_column(
    SAEnum(Frequency, native_enum=False, name="ck_series_frequency"),
    nullable=False,
)

# Schema
class SeriesCreate(BaseModel):
    frequency: Frequency
```

The DB stores the value as a `VARCHAR` with a named CHECK constraint. Adding new
enum values later requires a hand-written Alembic migration (autogenerate is
unreliable for CHECK changes). This tradeoff is accepted.

`tags` are the explicit exception: they are curated lookup data seeded into the
database, not Python enums, because application code does not branch on a fixed
tag taxonomy.

## Foreign-key deletion policy

Every V3 foreign key declares an explicit `ON DELETE` rule. The default is
`RESTRICT` for canonical entities, hierarchy links, lineage-bearing rows, and
audit/history rows. `CASCADE` is reserved for pure membership rows and owned
extensions that have no standalone meaning. The canonical per-edge policy lives
in `docs/schema/db_er.txt`; rationale lives in ADR 0008.

## Seed strategy

Alembic owns schema. A separate Typer CLI owns seed data. They do not mix.

Seed data lives in `src/macro_foundry/seed/data/` as typed Python (not YAML/JSON —
the data is curated by developers and benefits from type-checked enum constants).
Where the schema exposes a stable natural key (`geographies.code`, `tags.name`,
`providers.name`), runners use `INSERT ... ON CONFLICT DO UPDATE`. Where V3 does
not expose a uniqueness constraint (`provider_catalogs`, `geography_memberships`),
the seed runner reconciles by curated natural keys before insert/update. Re-running
`uv run macrodb seed` on an existing DB is safe and updates any fields whose
values have changed in the data files.

In-scope for this phase: geographies (ISO countries + major blocs + key
subnationals + selected subnational regions where curated)
and tags (the 7 fixed categories), plus a small default provider/provider-catalog
seed set. Concepts, series, and families still come later via the API/admin.

## Testing philosophy

Test the **generator and the constraints**, not every table individually.

With the CRUD generator pattern, the 80% of tables behave identically — testing
them all is wasted effort. Instead:

- 1 test: Alembic round-trip
- 3 tests: seed idempotency
- 8 tests: CRUD generator behavior (against one representative table — `concepts`)
- 10 tests: DB-level constraint enforcement (UNIQUEs, CHECKs, FKs, the view)
- 5 tests: hand-tuned route integration (series create, observations bulk, etc.)
- 1 test: end-to-end smoke (concept → family → series → source → observation → view)

Per-test transaction rollback for isolation. Seeds run once per session.

## Future directions, intentionally not built now

These are noted so they aren't accidentally pre-empted by current choices:

- **`series_composition_nodes`** for CPI baskets and budget breakdowns (deferred).
- **Materialized `latest_observations`** if the view becomes a hot path (current
  view is a regular view; can be swapped without API changes).
- **Cursor-based pagination on `observations`** (currently limit/offset).
- **Per-user auth, OAuth, JWT** (currently single bearer token).
- **PostgREST as a read-only second front door** for downstream consumers — an
  option once the schema stabilizes.
- **dbt for the derived-series transformation layer** — a real option later;
  in-Python computation is fine for now.
