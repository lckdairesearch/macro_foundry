# ADR 0006 — Two-role database architecture

**Status:** Accepted

**Date:** 2026-06-08

## Context

The application has multiple distinct consumers of the database: Alembic
migrations, the FastAPI app, SQLAdmin, ingestion scripts (later), and the test
suite. Granting all of them the same broad privileges is a security and
operational risk; one role for each is overkill at our scale.

We also wanted the architecture to translate cleanly from local Docker to Neon,
where the role model is constrained (no true superuser available to the
project owner).

## Decision

- **Two roles, separated by privilege:**
  - **`macrodb_owner`** — owns the schema. Has full DDL on the `public` schema
    (CREATE/ALTER/DROP on tables, views, functions, etc.). Used **only** by
    Alembic for migrations.
  - **`macrodb_app`** — used by FastAPI, SQLAdmin, ingestion (later), and tests.
    Has SELECT/INSERT/UPDATE/DELETE on all tables in `public`, plus USAGE on
    the schema. No DDL.
- **Separate connection strings:** `MACRODB_OWNER_URL` and `MACRODB_APP_URL`.
  Each role uses only its URL.
- **Roles created in `docker/postgres/init/01_roles.sql`** on first container
  boot. Both `macrodb` and `macrodb_test` databases get the same role set.
- **On Neon**, the project owner role serves as `macrodb_owner` equivalent;
  `macrodb_app` is created via SQL on first setup.

## Consequences

**Positive:**
- **Defense-in-depth.** If a route handler is exploited (SQL injection, etc.),
  the attacker cannot ALTER tables or DROP data — only manipulate row content.
- **Clear separation of concerns** in the codebase: anything that does DDL
  lives in Alembic and uses the owner URL. Everything else uses the app URL.
- **Migrations are explicit.** You can't accidentally write a route handler
  that issues DDL — the connection would fail.
- **Neon-portable.** Neon doesn't grant true superuser to project owners, but
  what they grant is sufficient for our `macrodb_owner` role. The architecture
  doesn't depend on superuser-only operations.
- **Audit-friendly.** Logs distinguish between schema changes (owner) and
  data operations (app).

**Negative:**
- Two URLs to manage instead of one. Mitigated by `pydantic-settings` handling
  both transparently.
- Setting up a new environment requires creating both roles, which is a one-time
  step that's automated for local (via `01_roles.sql`) but manual on Neon.

## Deferred: `macrodb_user` (read-only role)

A third read-only role was discussed for the eventual MCP / AI agent / external
consumer use case:

- **`macrodb_user`** — SELECT-only on all tables in `public`.

**This role is intentionally NOT created in this phase.** It's reserved for
when we have an MCP server, external read consumers, or a PostgREST front
door that warrants it. Creating it now would be premature — there's nothing
to use it.

When we add it, the principle is the same: a connection string
(`MACRODB_USER_URL`) and tightly-scoped privileges.

## Init SQL sketch

The init script (full version in `docker/postgres/init/01_roles.sql`) does
roughly:

```sql
-- Create databases
CREATE DATABASE macrodb;
CREATE DATABASE macrodb_test;

-- Create roles with passwords from env
CREATE ROLE macrodb_owner LOGIN PASSWORD '...';
CREATE ROLE macrodb_app LOGIN PASSWORD '...';

-- Owner role gets full ownership of both DBs
ALTER DATABASE macrodb OWNER TO macrodb_owner;
ALTER DATABASE macrodb_test OWNER TO macrodb_owner;

-- App role gets data access on both
\c macrodb
GRANT USAGE ON SCHEMA public TO macrodb_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO macrodb_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO macrodb_app;

\c macrodb_test
-- ...same grants for test DB
```

The `ALTER DEFAULT PRIVILEGES` is the trick: any tables Alembic creates as
`macrodb_owner` will automatically be readable/writable by `macrodb_app`,
without needing to re-grant after every migration.

## Alternatives considered

- **Single role for everything.** Simpler setup, but no defense-in-depth, no
  separation between schema and data operations.
- **Three roles from the start (owner / app / user).** Premature for this
  phase. Adding the third later is a small change; we'd rather defer.
- **Per-consumer roles** (one for FastAPI, one for SQLAdmin, one for ingestion,
  one for tests). Excessive at our scale. Their privileges would all be
  identical to `macrodb_app` anyway.
