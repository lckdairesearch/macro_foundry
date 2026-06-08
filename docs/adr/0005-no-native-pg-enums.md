# ADR 0005 — No native Postgres ENUM types

**Status:** Accepted

**Date:** 2026-06-08

## Context

Postgres has a native `ENUM` type that's distinct from `VARCHAR` with a CHECK
constraint. The choice between them affects how enum values evolve over time
in migrations and how the schema is represented at the DB level.

The V3 schema has ~25 columns documented as enums. This decision applies to
all of them uniformly.

## Decision

- **Do not use native Postgres ENUM types.**
- Use Python `str, Enum` classes as the source of truth, declared in SQLAlchemy
  via `Enum(MyEnum, native_enum=False, name="ck_<table>_<col>")`. This stores
  the value as `VARCHAR` with a named CHECK constraint.

See also: ADR 0002 for the full enum pattern.

## Consequences

**Positive:**
- **Adding a new value is a reversible operation.** Drop the CHECK constraint,
  recreate it with the new set of values. Both `upgrade()` and `downgrade()`
  are clean and transactional.
- **Renaming/removing values is feasible.** Native ENUMs make renames a
  multi-step ordeal involving creating a new type, copying columns, dropping
  the old type. With CHECK constraints it's just an ALTER.
- **Multiple environments evolve independently.** Local dev, staging, prod
  Neon can each get a new enum value at different times via standard migrations,
  without type-rebuild operations.
- **No special migration ceremony.** Standard `op.drop_constraint` /
  `op.create_check_constraint` calls.

**Negative:**
- **Alembic autogenerate is unreliable for CHECK changes** on `Enum(native_enum=
  False)` columns. Adding a value requires a hand-written migration. This is
  the known cost.
- We lose PG's native ENUM type system (which is mostly a representational
  niceness; behaves like a small lookup-table-of-types).
- The schema column type shows as `VARCHAR(N)` in `\d table` rather than the
  enum's name. Minor cosmetic issue.

## Migration template for adding an enum value

When you add a value to a Python enum, the corresponding Alembic migration is:

```python
def upgrade():
    op.drop_constraint("ck_series_seasonal_adjustment", "series", type_="check")
    op.create_check_constraint(
        "ck_series_seasonal_adjustment", "series",
        "seasonal_adjustment IN ('SA', 'SAAR', 'NSA', 'BSA', 'unknown')",
    )

def downgrade():
    op.drop_constraint("ck_series_seasonal_adjustment", "series", type_="check")
    op.create_check_constraint(
        "ck_series_seasonal_adjustment", "series",
        "seasonal_adjustment IN ('SA', 'SAAR', 'NSA', 'unknown')",
    )
```

Predictable, reviewable, reversible. The CHECK constraint name is stable, so
diff-based code review of the migration is easy.

## Alternatives considered

- **Native `postgresql.ENUM(...)` types.** Rejected for the evolution friction.
  `ALTER TYPE ... ADD VALUE` is non-transactional in some PG versions, can't
  be wrapped in a rolled-back transaction, and is irreversible without a full
  type rebuild.
- **Bare `String` columns with no DB-level enforcement, relying on Pydantic
  only.** Rejected because the DB is authoritative — an invalid value coming
  from any path (raw SQL, future agent, ingestion bug) should be rejected.
- **Lookup tables for every enum.** Heavy-handed. Most enums are code-routing
  values where adding a new value requires new code anyway, so the
  admin-extensibility benefit is illusory. Lookup tables are appropriate for
  `tags` (pure data) and the existing curated-taxonomy tables (`providers`,
  `concepts`, `geographies`).
