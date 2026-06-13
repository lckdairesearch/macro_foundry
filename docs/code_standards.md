# Code Standards

These are the rules that apply across the codebase. They are derived from the
architectural decisions in `architecture.md` and from the specific traps that
catch developers new to async SQLAlchemy + FastAPI + Neon.

When in doubt, follow these. When tempted to deviate, propose first.

## Python conventions

- **Python 3.12+.** Use modern syntax: `list[str]` not `List[str]`, `X | Y` not
  `Union[X, Y]`, `X | None` not `Optional[X]` (Optional is allowed but inconsistent;
  prefer `| None`).
- **Type hints are mandatory** on all public functions, class attributes, and
  Pydantic fields.
- **Imports** are absolute (`from macro_foundry.models import Series`), not relative.
- **No `print()`** in committed code. Use the project logger.
- **No `os.environ` direct access.** All config goes through `macro_foundry.config.settings`.
- **Lowercase snake_case** for variables, functions, modules. **PascalCase** for
  classes. **UPPER_SNAKE_CASE** for module-level constants and Enum values.

## SQLAlchemy patterns

### Models

- Use SQLAlchemy 2.x style: `Mapped[T]` + `mapped_column(...)`. No legacy
  `Column(...)` syntax.
- Models with a synthetic UUID primary key inherit from either `TimestampedBase`
  (id + created_at + updated_at) or `CreatedAtBase` (id + created_at only, for
  append-only tables like `observations` and run logs).
- V3 composite-key junction tables keep their schema-native keys instead of
  gaining a synthetic `id`. Today that applies to `concept_tags` and
  `indicator_variants`.
- `id` is always `uuid.UUID` with `server_default=text("uuidv7()")`. Never
  generate UUIDs in Python.
- `created_at` and `updated_at` are always server-side defaults
  (`server_default=func.now()`). `updated_at` additionally uses
  SQLAlchemy `onupdate=func.now()`. **No DB triggers.**
- FKs use `ForeignKey("table.id")` and `Mapped[uuid.UUID]`, whether open-coded
  in the model or centralized through the private helper seam. The relationship
  companion is declared separately as `Mapped["Target"] = relationship(...)`.
- Repeated column policy may be centralized only in the private module
  `src/macro_foundry/models/_schema_policy.py`. Keep the interface narrow:
  `fk_uuid(target, *, ondelete, nullable)` for UUID foreign keys, and no
  relationship, PK, CHECK, or UNIQUE helpers.
- UNIQUE constraints (single-column or composite) live in `__table_args__`,
  not as `unique=True` on the column (consistency).
- CHECK constraints (cross-column) live in `__table_args__` as `CheckConstraint(...)`.
- All ENUM columns use `SAEnum(MyEnum, native_enum=False, name="ck_<table>_<col>")`,
  whether open-coded or returned by the private helper seam. Never `String`
  with manual CHECK; never native PG enum.
- Repeated enum policy may be centralized only in the private module
  `src/macro_foundry/models/_schema_policy.py` as
  `enum_column(table_name, column_name, enum_type, *, nullable)`. Keep
  `table_name`, `column_name`, and `nullable` explicit at the call site so the
  CHECK-constraint name remains obvious in the model module.

### Sessions

- **Async only.** No `Session`, only `AsyncSession`.
- **`expire_on_commit=False`** on the sessionmaker. Required, not optional.
- **`autoflush=False`** on the sessionmaker. Explicit control.
- **`get_session()` dependency** yields one session per request, rolls back on
  exception, closes in the `finally`.

### Queries

- **No lazy loading. Ever.** Every relationship access in a route handler must
  have been eager-loaded by `selectinload` or `joinedload`. If you see
  `MissingGreenlet` in an error, fix the query to eager-load.
- Use `select(...)` not `session.query(...)`. SQLAlchemy 2.x style.
- For `latest_observations`, query the view directly via a model class mapped to
  it, or via `text("SELECT ... FROM latest_observations WHERE ...")` for ad-hoc.
- Bulk inserts use `session.add_all(...)` for small batches; for `observations`
  bulk endpoints, use Core-level `insert(Observation).values([...])` with
  `on_conflict_do_nothing` or `on_conflict_do_update` as appropriate.

## Pydantic patterns

- **Pydantic v2 only.** `model_config = ConfigDict(from_attributes=True)` on Read
  schemas (replaces v1's `orm_mode`).
- **Four variants per table where applicable:** `XBase`, `XCreate`, `XUpdate`,
  `XRead`. Optionally `XReadDetail` for endpoints that return nested relations.
- **`Update` does NOT inherit from `Base`.** All fields explicitly optional,
  defaulted to `None`. This makes PATCH semantics clean.
- **Cross-field validators** mirror DB CHECK constraints. Use
  `@model_validator(mode="after")` so they run after individual field validation.
- **Enums** are imported from `macro_foundry.enums` and used directly as field
  types. Same enum class as the model, no duplication.
- **`UUID` and `datetime`** are imported from `uuid` and `datetime`.

## FastAPI patterns

- **All routes are `async def`.**
- **Session dependency** is `session: AsyncSession = Depends(get_session)`.
- **Auth dependency** is `_=Depends(verify_token)` for all API routes (the
  underscore-named result discards the return; auth's effect is the exception
  it would have raised).
- **Response models** are declared via `response_model=XRead` on the route
  decorator, not just in type hints.
- **Status codes** are explicit: `status_code=status.HTTP_201_CREATED` on POST,
  `status_code=status.HTTP_204_NO_CONTENT` on DELETE.
- **Error responses** use `HTTPException` with explicit status codes; never
  return `{"error": ...}` dicts.
- **Path operations** stay thin. Cross-field validation lives in Pydantic;
  database constraints live in SQLAlchemy; business logic in the route is fine
  for simple things, factored into a service function once it grows.

## CRUD generator usage

- Simple tables register the generator in one line in their router file.
- A table opts out by not calling `crud_router` and writing its routes by hand.
- **Don't modify the generator to handle a special case** — the special case
  goes in a hand-written route instead. The generator stays simple and predictable.

## SQLAdmin patterns

- Every concrete `ModelView` inherits from `BaseModelView` (in
  `backend/admin/_base.py`).
- `form_excluded_columns` always includes `["id", "created_at", "updated_at"]`.
- FKs displayed in list view use `column_formatters` to show a meaningful label
  (`m.geography.code` or `m.geography.name`), not the UUID.
- JSONB columns get a textarea widget via `form_widget_args`.
- Custom dashboards, bulk actions, inline editing of relations — **not in this
  phase.** Defer.

## Alembic patterns

- **Migrations run as `macrodb_owner`** (via `MACRODB_OWNER_URL`).
- **Autogenerate is the starting point, not the end.** Always review the
  generated migration before applying. Check that CHECK constraints landed,
  that UNIQUE constraints are named, that the view migration is hand-written.
- **The `latest_observations` view** is created in its own hand-written migration
  immediately after the initial autogenerated schema migration. Both `upgrade()`
  and `downgrade()` use raw SQL.
- **Enum value additions** require hand-written migrations that DROP the old
  CHECK constraint and CREATE the new one. Autogenerate cannot reliably detect
  this for `native_enum=False` columns.
- **Migration names are descriptive** (`add_seasonal_adjustment_bsa`,
  not `migration_4`).

## Testing patterns

- **Async fixtures only.** `@pytest_asyncio.fixture` on all DB-touching fixtures.
- **Session-scoped `test_engine`** sets up `macrodb_test`, runs migrations, runs
  seeds. Once per pytest session.
- **Per-test `session` fixture** uses a SAVEPOINT-rolled-back transaction so each
  test sees a clean state without re-running setup.
- **The `client` fixture** is an `httpx.AsyncClient` with the FastAPI app and
  `get_session` overridden to use the test session.
- **Tests assert constraint violations as exceptions**, not as return values.
  `with pytest.raises(IntegrityError): ...`
- **No mock SQLAlchemy.** We test against a real Postgres test database. Mocking
  the ORM gives false confidence.

## Seed patterns

- Data files in `src/macro_foundry/seed/data/` are typed Python (lists of dicts,
  with values from the enum classes). Not YAML, not JSON.
- Runners use `insert(Model).values(...).on_conflict_do_update(...)`. Always
  idempotent.
- The CLI orchestrator runs runners in dependency order: geographies before
  geography_memberships, base tables before junctions.
- `macrodb seed --dry-run` logs what would change without committing.
- `macrodb seed --reset` requires `--confirm` and is destructive; use only on
  dev DBs.

## Config and secrets

- `.env.local` is the single source of secrets locally. Always gitignored.
- `.env.example` ships with placeholder values, committed.
- `pydantic-settings` reads `.env.local` once into a typed `Settings` object.
  Everything else imports `from macro_foundry.config import settings`.
- **Never log connection strings, API keys, or passwords.**
- Production secrets (Neon, eventually any provider API keys, the bearer token,
  admin credentials) live on the host's env, not in `.env.local`.

## Logging

- Use the project logger, configured in `macro_foundry.config`.
- Log levels: `DEBUG` (verbose internal state), `INFO` (lifecycle events),
  `WARNING` (recoverable issues), `ERROR` (failed operations), `CRITICAL`
  (system-down).
- Never log secrets, full request bodies, or PII.
- For ingestion runs (later), log to the database in `ingestion_run_logs` plus
  to stdout via the logger.

## Things that look right but are wrong

A few common traps. If you find yourself doing any of these, stop:

- ❌ `s.geography.code` in a route handler without having eager-loaded `geography`
  — will raise `MissingGreenlet`.
- ❌ `await session.commit()` followed by `return obj` — works only because
  `expire_on_commit=False`; if you ever remove that flag, this breaks silently.
- ❌ Creating a new `AsyncSession()` inside a route — use the dependency.
- ❌ Putting a `String` column with `CheckConstraint("col IN ('a','b')")` in
  `__table_args__` instead of using `SAEnum(MyEnum, native_enum=False, ...)`.
  Loses Pydantic-side validation.
- ❌ `default=uuid.uuid4` on the `id` column — we use server-side `uuidv7()`.
- ❌ Native PG enum types (`postgresql.ENUM(...)`) — we explicitly don't use them.
- ❌ A bare `await session.execute(...)` followed by accessing `.scalars()` on
  the result without `await` — `.scalars()` is sync; `result = await session.execute(...);
rows = result.scalars().all()` is the right pattern.
- ❌ Storing Pydantic models in SQLAlchemy columns directly — convert via
  `.model_dump()` on insert.

## File-naming conventions

- Modules: `lower_snake_case.py`, plural for collections (`schemas/series.py`
  contains `SeriesCreate`, `SeriesRead`, etc.).
- Test files: `test_<thing>.py`, mirrors the module being tested where
  applicable.
- Migration files: Alembic-generated names; rename for clarity if needed
  (`0003_add_seasonal_adjustment_bsa.py`).
- Seed data files: descriptive (`data/geographies.py`, `data/tags.py`).

## When unsure

1. Check `CONTEXT.md` for terminology.
2. Check `architecture.md` for the layer's purpose.
3. Check `docs/adr/` for whether the decision has been made.
4. Check `code_standards.md` (this file) for the rule.
5. If still unsure, **ask the user.** Do not guess.
