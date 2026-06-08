# ADR 0009 — Physical database naming by environment

**Status:** Accepted

**Date:** 2026-06-08

## Context

The repo originally documented the local working database as `macrodb` and the
local test database as `macrodb_test`, while also implying future cloud
dev/staging use on Neon. That created two overlapping meanings for `macrodb`:

- the logical database / system name used throughout the project language
- the literal physical Postgres database name

As the environment model became clearer, the ambiguity became costly. Local
development and local tests are distinct environments, while cloud production is
the only cloud environment currently intended. We wanted the physical database
names to make that separation obvious without redesigning the config surface or
changing the two-role architecture.

## Decision

- **Keep `macrodb` as the logical database/system name.**
- **Use environment-specific physical Postgres database names:**
  - local development: `macrodb_dev`
  - local tests: `macrodb_test`
  - cloud production: `macrodb_prod`
- **Do not introduce new environment-specific URL variable names.**
  Keep the existing config surface:
  - `MACRODB_OWNER_URL`
  - `MACRODB_APP_URL`
  - `MACRODB_TEST_URL`
- **Locally,** `MACRODB_OWNER_URL` and `MACRODB_APP_URL` point to
  `macrodb_dev`, while `MACRODB_TEST_URL` points to `macrodb_test`.
- **In cloud production,** `MACRODB_OWNER_URL` and `MACRODB_APP_URL` point to
  `macrodb_prod`.
- **There is no cloud dev/staging database in the current architecture.**
- **Local Docker bootstrap creates only `macrodb_dev` and `macrodb_test`.**
  It does not create `macrodb_prod` locally.
- **Cloud `macrodb_prod` creation is an explicit infrastructure step outside
  this repo.**

This ADR supersedes the physical database naming examples in ADR 0006, but not
the two-role split itself.

## Consequences

**Positive:**
- The physical database names now communicate environment purpose directly.
- The logical term `macrodb` remains stable across docs, CLI, and domain
  language.
- We avoid a config-surface redesign; existing code still reads the same three
  URL settings.
- Tests stay clearly isolated from the working database.

**Negative:**
- Existing local users must recreate their local Postgres volume to pick up the
  renamed databases; a plain container restart is not enough.
- The cloud environment is intentionally asymmetric with local: one production
  database only, no cloud staging for now.

## Alternatives considered

- **Keep `macrodb` locally and document the ambiguity.** Rejected because the
  ambiguity is exactly what causes confusion.
- **Rename local `macrodb` to `macrodb_test`.** Rejected because it would
  collapse the distinct dev/test environments rather than clarify them.
- **Introduce `MACRODB_DEV_URL` / `MACRODB_PROD_URL` env vars.** Rejected
  because the existing owner/app/test URL surface is sufficient and already
  wired through the codebase.
- **Create cloud dev/staging alongside `macrodb_prod`.** Rejected for now
  because the chosen environment model is local dev + local test + cloud prod.
