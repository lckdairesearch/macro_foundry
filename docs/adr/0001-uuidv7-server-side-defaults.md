# ADR 0001 — uuidv7 server-side defaults

**Status:** Accepted

**Date:** 2026-06-08

## Context

Postgres 18 ships with a native `uuidv7()` function. UUIDv7 is time-ordered:
the high bits are a Unix timestamp, so primary key inserts are roughly sequential
rather than randomly distributed (as with UUIDv4). This means much less B-tree
fragmentation on the PK index, better cache locality, and indirectly better
INSERT performance at scale.

We needed to decide:
1. UUIDv7 or stick with UUIDv4 (or another scheme like ULID or bigserial)?
2. Generate the UUID server-side (in the DB) or client-side (in Python)?
3. How to express this in SQLAlchemy?

## Decision

- **Use `uuidv7()` for all PK and FK columns.** Native PG18 function. No
  extension needed.
- **Generate server-side via `server_default=text("uuidv7()")`.** SQLAlchemy
  retrieves the generated value via RETURNING automatically.
- **No client-side `default=uuid.uuid4` or `default=uuid7()` from a Python
  library.** Single source of truth: the DB.

In SQLAlchemy:
```python
id: Mapped[uuid.UUID] = mapped_column(
    UUID(as_uuid=True),
    primary_key=True,
    server_default=text("uuidv7()"),
)
```

Factored into `TimestampedBase` and `CreatedAtBase` mixins so it's declared once.

## Consequences

**Positive:**
- Sequential-ish PK inserts → smaller index size, faster bulk inserts.
- `id` and `created_at` are loosely correlated (both monotonic), useful for
  debugging and for some pagination strategies.
- No collisions across instances (UUID guarantees still hold).
- One source of UUIDs — the DB. Removes a category of "did I generate it before
  or after the insert?" questions.

**Negative:**
- Client cannot know the ID before INSERT. For the rare case where this matters
  (e.g. logging a "creating series ID X" message before the row exists), we'd
  need to either generate client-side ad-hoc or refactor the log. Not common.
- UUIDv7 is a newer format; some downstream tooling (older client libraries,
  some SQL admin tools) may display them without special handling. Not a real
  problem at our scale.

## Alternatives considered

- **UUIDv4 (random).** Standard, well-supported. Rejected for the index
  fragmentation issue at scale.
- **bigserial / auto-increment integers.** Smaller, faster. Rejected because
  they leak sequencing information (you can guess the row count) and are
  awkward for distributed inserts.
- **ULID.** Time-ordered like UUIDv7. Rejected because PG18's native uuidv7
  makes it strictly worse — adopting ULID would require an extension or a
  client-side library.
- **Client-side UUID generation.** Rejected because it creates two sources of
  truth and forces every insert path to know about UUID generation.
