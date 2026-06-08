# ADR 0003 — Thin in-repo CRUD generator over PostgREST / Supabase / Django / SQLModel

**Status:** Accepted

**Date:** 2026-06-08

## Context

V3 has 19 tables. Most are pure CRUD; a few have real semantic logic (`series`,
`observations`, the proposal lifecycle). We needed a strategy for exposing them
as an API without writing 90 repetitive route handlers and 60+ schema classes
by hand, while preserving control over the routes that need it.

The realistic options:

1. **Fully hand-written** — every schema, every route by hand.
2. **External CRUD library** — `fastapi-crudrouter` or similar.
3. **SQLModel** — combine SQLAlchemy and Pydantic into one class.
4. **PostgREST or Supabase** — auto-generate the API from the schema.
5. **Thin in-repo CRUD generator** — write a ~150-line factory ourselves.

This decision also touches whether we adopt a different stack philosophy
entirely (PostgREST/Supabase) or stay with FastAPI as the front door.

## Decision

- **Thin in-repo CRUD generator + hand-tuned hotspots.** A `crud_router(model,
  create_schema, update_schema, read_schema, ...)` factory in
  `src/macro_foundry/backend/crud.py` (~150 lines) produces standard
  GET-list / GET-by-id / POST / PATCH / DELETE routes with consistent
  conventions (404 handling, pagination, error shape).
- **Simple tables (~15 of 19)** register via one-liner: `router = crud_router(
  model=Concept, create_schema=ConceptCreate, ...)`.
- **Complex tables** (`series` with cross-field validation, `observations` with
  bulk insert and vintage handling, governance lifecycle endpoints) get
  hand-written routes that don't use the generator.
- **Pydantic schemas are hand-written** with the `Base / Create / Update / Read`
  variant pattern. Validation lives there, not in the generator.

## Consequences

**Positive:**
- Consistent behavior across the CRUD-able 80% of tables — same conventions,
  same pagination, same error responses.
- Full control where it matters; hand-written routes can do anything they need.
- No external dependency to maintain. The generator is our code, simple to
  read and modify.
- Pydantic schemas remain hand-written, which is correct — that's where
  cross-field validation (mirroring DB CHECKs) lives.
- About one week of work for the whole backend, instead of three.

**Negative:**
- Designing the generator takes 1-2 days of careful engineering. The abstraction
  has to be just right or it gets in the way of edge cases.
- Future maintainers need to learn the generator's interface. Mitigated by
  keeping it small (~150 lines) and well-commented.
- Refactoring the generator can ripple across the simple-table routers.
  Mitigated by the fact that simple tables only use the generator as a
  one-liner; the surface area of impact is small.

## Alternatives considered

- **Fully hand-written.** Real time investment (2-3 weeks). High risk of
  drift between endpoints (different 404 styles, pagination schemes,
  error shapes). The repetition is grinding work, not interesting work.
- **External CRUD library (`fastapi-crudrouter` etc.).** Most aren't maintained
  well; `fastapi-crudrouter` lags on SQLAlchemy 2.x async. Leaky abstractions
  when you need custom logic — and we need custom logic on the interesting
  tables. Maintenance risk on a dependency that touches every route is not
  worth the time saved.
- **SQLModel.** Combines ORM and Pydantic in one class. Async support is rougher
  than raw SQLAlchemy 2.x; for non-trivial work you still need separate
  Create/Update/Read variants, so the "one class" promise breaks down. The
  complex models we'll write (`series`, `observations`) benefit from full
  SQLAlchemy expressiveness. Net-net not worth switching.
- **PostgREST / Supabase / Hasura.** Wrong validation philosophy for a curated
  layer. macrodb's structured validation rules (`origin_type='ingested' →
  requires a series_source`, `measure='growth' → requires measure_horizon`,
  dedup against existing codes, etc.) would have to live in plpgsql functions
  or a parallel Python service. The future AI agent will also write through
  these endpoints; sharing validation logic between API and agent is far easier
  in Python than via PostgREST + plpgsql. Read-side fit is excellent but the
  write side is where macrodb's logic lives.
- **Django + DRF.** Better admin (Django admin > SQLAdmin), but SQLAlchemy 2.x
  beats Django ORM significantly for the query patterns macrodb needs (CTEs,
  window functions, DISTINCT ON, recursive joins for future composition trees).
  Not worth losing SQLAlchemy to gain a better admin.

## Future direction

Once the schema stabilizes, **PostgREST as a read-only second front door**
becomes attractive. Stand it up in front of the `macrodb_user` (future
read-only role) and downstream consumers (frontend, MCP, external tools) get
a generic REST API for free. FastAPI remains the write path. Defer until
there's a real read consumer that warrants it.
