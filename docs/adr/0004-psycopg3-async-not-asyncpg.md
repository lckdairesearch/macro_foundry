# ADR 0004 — psycopg3 async over asyncpg

**Status:** Accepted

**Date:** 2026-06-08

## Context

For an async SQLAlchemy stack on Postgres, the two real driver choices are
`asyncpg` and `psycopg3` (which has both sync and async APIs). They have
materially different characteristics, and the choice affects how connection
pooling works on Neon and how ingestion scripts (sync) share dialect knowledge
with the API (async).

We needed to pick one and stay with it.

## Decision

- **Use `psycopg3` for both sync and async paths.** Connection strings use
  `postgresql+psycopg://...` for both. The async-vs-sync distinction happens
  in the engine creation (`create_async_engine` vs `create_engine`), not in
  the driver URL.

In `src/macro_foundry/db/session.py`:
```python
async_engine = create_async_engine(
    settings.db.app_url,  # postgresql+psycopg://...
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
)
```

## Consequences

**Positive:**
- **Unified driver family.** Sync ingestion scripts (later phase) and async API
  share the same dialect, same parameter parsing, same type coercion. No "wait,
  asyncpg formats this differently" bugs.
- **Forgiving with Neon's pooler.** `psycopg3` doesn't aggressively use prepared
  statements the way `asyncpg` does, so it doesn't hit the PgBouncer-
  transaction-mode incompatibility. We can use Neon's direct endpoint with
  normal SQLAlchemy pooling, and if we ever need the pooled endpoint we can
  switch without driver-level changes.
- **psycopg3 is the long-term direction** for Postgres in Python. Active
  development, maintained by the original psycopg2 author (Daniele Varrazzo).
- **Better type support** than asyncpg out of the box (Pydantic-compatible
  type handling, more flexible custom adapters).

**Negative:**
- **~20-30% slower than `asyncpg`** in tight-loop benchmarks. Real but not a
  problem at macrodb's scale (observations are inserted in batches, not in
  tight per-row loops; reads are typically a few hundred rows per request).
  If we ever hit a real perf wall, we can switch the async engine to asyncpg
  without changing the rest of the code.
- Slightly less battle-tested in async mode than asyncpg (asyncpg has been
  the de-facto choice for years), though psycopg3 async is mature as of 2024+.

## Alternatives considered

- **asyncpg.** ~20-30% faster, mature, widely used. But:
  - Requires `statement_cache_size=0` under PgBouncer transaction mode (which
    Neon's pooled endpoint uses). This is a known incompatibility.
  - Forces a different driver from any sync code in the project. Ingestion
    scripts would either use `psycopg` (split-brain) or be rewritten as async
    (premature complexity).
  - Has its own quirks around custom type adaptation that psycopg3 handles
    more uniformly.
- **psycopg2 (sync only).** Legacy. Async story requires `psycopg2 + aiopg`,
  which is unmaintained. Pass.

## Engine configuration rationale

The pool settings (`pool_pre_ping=True`, `pool_recycle=300`, `pool_size=5`,
`max_overflow=10`) are specifically tuned for Neon's scale-to-zero behavior:

- **`pool_pre_ping=True`** — validates the connection before checkout. Without
  it, the first request after Neon's compute suspends (~5 min idle) gets a
  dead connection.
- **`pool_recycle=300`** — recycles connections every 5 minutes. Belt-and-
  braces with pre_ping; ensures connections don't outlive Neon's idle window.
- **`pool_size=5, max_overflow=10`** — small pool because Neon has per-instance
  connection limits and we'll likely run multiple app instances eventually.

For local development, these settings are slightly conservative but cause no
problems.
