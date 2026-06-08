# ADR 0002 — Enum / CHECK constraint pattern

**Status:** Accepted

**Date:** 2026-06-08

## Context

The V3 schema has ~25 columns documented as enums (e.g. `frequency`, `measure`,
`seasonal_adjustment`). We needed a single decision that applies across all of
them, covering:

1. How enum values are enforced at the DB level (native PG ENUM type, CHECK
   constraint, or no enforcement)?
2. How the enum values are exposed to the application (Python `Enum` classes,
   bare strings, generated constants)?
3. How Pydantic schemas and SQLAlchemy models share the same definition?
4. How new enum values are added later?

There's a tension between rigidity (catch bad values at the DB) and evolvability
(adding a new value should be cheap).

## Decision

- **Python `str, Enum` classes are the single source of truth.** Organized by
  domain in `src/macro_foundry/enums/`.
- **SQLAlchemy uses `Enum(MyEnum, native_enum=False, name="ck_<table>_<col>")`.**
  This stores the value as `VARCHAR` and emits a named `CHECK` constraint
  enforcing the allowed values.
- **Pydantic uses the same Python `Enum` class directly as a field type.** No
  duplicate enum definitions between models and schemas.
- **Tags are the one exception.** `tags.name` has only a `UNIQUE` constraint
  (no CHECK), because the tag taxonomy is curated data, not a code-routing enum.
  Initial values come from seed data; admins can add new ones via SQLAdmin.

In SQLAlchemy:
```python
frequency: Mapped[Frequency] = mapped_column(
    SAEnum(Frequency, native_enum=False, name="ck_series_frequency",
           validate_strings=True, length=16),
    nullable=False,
)
```

In Pydantic:
```python
from macro_foundry.enums.series import Frequency

class SeriesCreate(BaseModel):
    frequency: Frequency
```

## Consequences

**Positive:**
- One Python class defines the enum; models, schemas, and SQLAdmin all share it.
- DB enforces values via CHECK — bad data can't enter even via raw SQL.
- Adding a new enum value is a deliberate operation: edit the Python enum, write
  a small Alembic migration to update the CHECK, deploy.
- Cross-column CHECKs (e.g. `measure='growth' → measure_horizon NOT NULL`) live
  in the same `__table_args__` block, consistent with single-column CHECKs.

**Negative:**
- **Alembic autogenerate is unreliable for CHECK changes** on
  `Enum(native_enum=False)` columns. Adding a value requires a hand-written
  migration (drop the old constraint, create the new one with the expanded set).
  Not a daily problem — enum changes are rare — but a known friction.
- We don't get PG's native `ENUM` performance optimizations (which are minor
  anyway at our scale).

## Alternatives considered

- **Native PG ENUM types.** Rejected for the rigidity of value-addition. `ALTER
  TYPE ... ADD VALUE` is non-transactional in some PG versions and irreversible
  without a full type rebuild.
- **Bare `String` columns with manual `CheckConstraint` in `__table_args__`.**
  Rejected because it loses the SQLAlchemy-side validation: assigning an invalid
  value to an attribute wouldn't fail until INSERT. The `Enum(native_enum=False)`
  approach gives both ORM-level and DB-level enforcement.
- **No enforcement at the DB layer, validate only in Pydantic.** Rejected because
  the DB is the source of truth; an enum constraint should be enforced regardless
  of which path inserts the data (FastAPI, SQLAdmin, raw SQL, future agent).
- **Promoting more enums to lookup tables (admin-extensible).** Considered. The
  rule we settled on: promote to a lookup table when the values are pure curated
  data and no code branches on them. Currently only `tags.name` qualifies.
  Anything code branches on (`Frequency`, `Measure`, etc.) stays as a Python
  enum because adding a value would require new code anyway.
