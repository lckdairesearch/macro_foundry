# Progress Tracker

This file is the living record of what's been done. Update it when a phase
completes, when something deviates from the build plan, or when a handoff
between sessions happens.

Format per entry: `[YYYY-MM-DD] Phase N — Status. Notes.`

Most recent at the top.

---

## Current phase

**Phase 4 — Enums** (next).

Phase 3 is complete. The repo now has typed settings, shared SQLAlchemy base
mixins, and async session wiring validated against the local Postgres instance.

## Phase status

| Phase | Title                          | Status         |
| ----- | ------------------------------ | -------------- |
| 0     | Agent infrastructure           | ✅ Complete    |
| 1     | Repo bootstrap                 | ✅ Complete    |
| 2     | Docker + Postgres + roles      | ✅ Complete    |
| 3     | Config + session + base        | ✅ Complete    |
| 4     | Enums                          | ⏳ Next        |
| 5     | Models                         | ⏳             |
| 6     | Alembic + initial migrations   | ⏳             |
| 7     | Pydantic schemas               | ⏳             |
| 8     | Seed data + CLI                | ⏳             |
| 9     | CRUD generator + simple routes | ⏳             |
| 10    | Hand-tuned routes              | ⏳             |
| 11    | SQLAdmin                       | ⏳             |
| 12    | Tests                          | ⏳             |
| 13    | Neon parity verification       | ⏳             |

## Log

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
- corrected the `docs/CONTEXT.md` references in `architecture.md` and
  `build_plan.md` to `docs/glossary.md`, which matches the repo and `AGENTS.md`
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
- `docs/project_overview.md`, `docs/architecture.md`, `docs/code_standards.md`,
  `docs/glossary.md`, `docs/build_plan.md`, `docs/progress_tracker.md`
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
