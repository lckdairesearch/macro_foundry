# ADR 0020 — Catalog embeddings for semantic search

**Status:** Proposed

**Date:** 2026-06-12

## Context

ADR 0019 introduces a `check_db` node in the onboarding graph whose job
is to detect catalog duplicates from a descriptive brief that carries
no canonical code or identifier. To do that job at all, `check_db`
needs a candidate-retrieval surface that operates in meaning-space, not
character-space: the briefed series might be described as "headline
inflation rate, monthly, United States" while the matching catalog row
is named "Consumer Price Index for All Urban Consumers". No amount of
trigram or alias-based fuzzy matching closes that gap reliably; only
semantic comparison does.

The macrodb catalog at steady state is small (target ~200 series, a few
dozen families and concepts) but the failure modes that `check_db` is
designed to prevent — silent duplication, trivial-transformation
duplication, missed supersede candidates — are about **meaning**, not
scale. The right primitive is therefore embedding-based similarity.

Three properties of the codebase shape the design:

- Catalog rows are created by **multiple paths**: the FRED bootstrap
  (`src/macro_foundry/bootstrap/fred_us_macro.py`), the MCP
  write-enabled tool `apply_approved_proposal`, any future ingestion
  runner, and occasional SQLAdmin entries. An embed-on-write
  mechanism that lives in the agent layer would silently skip every
  other path.
- ADR 0011 forbids agents reaching the catalog through anything other
  than `macrodb-mcp`. The new search surface is therefore an MCP
  read-tool concern, not a generic Postgres-MCP concern.
- ADR 0005 / CLAUDE.md forbid DB triggers and require Neon-portable
  behavior. The embed-on-write mechanism therefore lives at the
  Python service layer, not in `pg_cron`, not in a trigger, and not
  in a sidecar process.

## Decision

The catalog is extended with per-row text embeddings on three tables —
`concepts`, `series_families`, and `series` — populated by a
service-function registration path, consumed by a similarity-search
surface on the read-only MCP, and kept honest by a versioning scheme
that mechanically detects stale embeddings.

### Scope

Embedded tables: `concepts`, `series_families`, `series`. These are the
three semantic-entity tables `check_db` reasons over.

Not embedded: `providers`, `provider_catalogs`, `ingestion_feeds`,
`series_sources`, `geographies`, `tags`, `observations`. These are
either operational configuration, exact-key lookups, the prefilter
itself, or numerical timeseries data. Re-evaluating any of these later
is a new ADR.

### Model and dimensionality

Embeddings are produced by OpenAI **`text-embedding-3-small` at the
default 1536 dimensions**. No Matryoshka truncation; storage at
catalog scale is a rounding error and we prefer the full dimensional
fidelity. `text-embedding-3-large` was considered and rejected on the
grounds that no measurable recall gain accrues at this catalog size
and domain.

The model name is **not implicit**. Every embedded row records the
exact model identifier it was produced by, so model swaps are
detectable and trigger a backfill rather than silently mixing
embedding spaces.

### Schema changes

A single Alembic migration as `macrodb_owner` does the following:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Adds three columns to each of `concepts`, `series_families`, `series`:

- `embedding vector(1536)` — the embedding itself, nullable.
- `embedding_model text` — the model identifier that produced it
  (e.g. `"text-embedding-3-small"`), nullable.
- `embedding_input_hash text` — a stable hash of the composed input
  text that the embedding was produced from, nullable.

Creates one HNSW index per embedded table over `vector_cosine_ops`.
HNSW is chosen over IVFFlat for read-dominated workloads; default
parameters are sufficient at this scale. The index is created even
though the catalog is small, so no later migration is needed when the
catalog grows.

Neon support for `pgvector` is a prerequisite; this has been verified
for the staging target.

### Embed-input composition

For each embedded table, a **pure function** in
`src/macro_foundry/services/embeddings.py` composes the row's embedding
input text from the row's own descriptive fields and its parents'
context:

- `compose_concept_embedding_input(concept) -> str`
- `compose_family_embedding_input(family) -> str`
- `compose_series_embedding_input(series) -> str`

Each function emits a structured natural-language description (label
lines such as `"Concept:"`, `"Description:"`, `"Frequency:"`) so the
embedding model sees both the values and their relationship. Series
composition includes the names of the parent family and concept;
family composition includes the parent concept; concept composition
stands alone.

The composed text is hashed (SHA-256 hex prefix is sufficient) into
`embedding_input_hash`. A row is considered up-to-date when:

```
row.embedding IS NOT NULL
AND row.embedding_model = current_model_id()
AND row.embedding_input_hash = sha256(compose(row))
```

This is the only mechanism by which staleness is detected. There is
no second source of truth.

### Embed-on-write service path

All catalog mutations of embedded tables go through service functions
in `src/macro_foundry/services/registration.py`:

- `register_concept(session, payload) -> Concept`
- `register_family(session, payload) -> SeriesFamily`
- `register_series(session, payload) -> Series`

Each function: validates the payload, composes the embedding input,
calls `embed_text(text) -> vector` (a thin async OpenAI client with a
single retry), persists the row with `embedding`, `embedding_model`,
and `embedding_input_hash` populated atomically, and returns the
saved row.

Callers refactored to use these helpers:

- `src/macro_foundry/bootstrap/fred_us_macro.py`
- The MCP write tool `apply_approved_proposal` in
  `src/macro_foundry/mcp/write_tools.py`
- Any future ingestion runner

Direct `session.add(Series(...))` patterns in the registration path
are removed. The model classes remain plain SQLAlchemy declarative
classes — the embedding logic is not in the ORM.

If the OpenAI call fails, the write fails. Operator intervention or
`backfill` cleans up. Silent partial writes are not allowed.

### Backfill CLI

A new command `macrodb embeddings backfill` scans each embedded table
for rows where the up-to-date predicate is false and re-embeds in
batches. It is used in four situations:

- One-time, on first deployment of this ADR, to embed rows that
  existed before this ADR.
- After an embed-input composition change.
- After a model swap.
- Recovery, when an embed-on-write failure left a row stale.

The command is idempotent and safe to run repeatedly. It sits under
the existing `macrodb` CLI alongside `macrodb db migrate` and
`macrodb serve mcp`.

### MCP read surface — similarity-search tools

The read-only `macrodb-mcp` server gains three tools:

- `search_concepts(query: str, limit: int = 10)`
- `search_series_families(query: str, limit: int = 10)`
- `search_series(query: str, limit: int = 10)`

Each tool internally:

1. Embeds `query` using the same model and the same client as the
   write path.
2. Optionally narrows by tag overlap if `query` contains
   tag-implying terms (the prefilter is best-effort, not required).
3. Runs cosine similarity (`vector_cosine_ops` `<=>`) against the
   table's embedding column, ordered ascending.
4. Returns the top-`limit` candidates with their full descriptive
   payload (the same shape as the existing `*Read` Pydantic schemas)
   plus a `similarity` score in `[0.0, 1.0]`.

Returning a similarity score with each candidate is non-optional: the
agent uses it as a soft prior in its reasoning, and downstream
verifiers can audit whether the search surface is performing.

These three tools are added to `READ_ONLY_TOOL_NAMES` in
`src/macro_foundry/mcp/server.py` and bound via `_register_read_tools`.
The existing exact-key lookups remain — they are the drill-down
surface that the agent uses after similarity search yields candidates.

### Update semantics

When an embedded row is mutated by a non-registration path (for
example, a curator-edited `description` via SQLAdmin), the row's
`embedding_input_hash` no longer matches the live composition and the
row is treated as stale. The next `backfill` run repairs it.
SQLAlchemy events are **not** used to auto-re-embed on update; the
explicit backfill semantics are simpler to reason about and harder to
get into a half-updated state.

### Configuration

A new environment variable `OPENAI_API_KEY` is required at any path
that may write to embedded tables. The MCP server and the bootstrap
both fail fast with a clear error if it is missing. The variable is
recorded in `.env.example` with a placeholder value.

The model identifier is a constant in
`src/macro_foundry/services/embeddings.py` (`EMBEDDING_MODEL =
"text-embedding-3-small"`). Changing it is a code change, intentional,
and triggers backfill on the next deployment.

### Non-goals

- This ADR does not redesign the registration flow for non-embedded
  tables (providers, geographies, ingestion_feeds). Their existing
  insert paths are unchanged.
- This ADR does not introduce cross-language matching, multi-modal
  embeddings, or learned re-rankers. These are not needed at the
  current catalog size and domain.
- This ADR does not move `pgvector` work to background jobs or
  queues. Embeddings at this scale are fast enough to handle
  synchronously inside the registration call.

## Consequences

**Positive:**

- `check_db` (ADR 0019) is unblocked with a candidate-retrieval
  surface that operates on meaning rather than character similarity.
- The catalog-wide embedding capability the operator has been planning
  for — for future search, recommendation, and observability use cases
  — lands as a side effect of this work, not as a separate project.
- All write paths share a single embedding implementation. The
  bootstrap, the agent's write tool, and any future runner cannot
  drift apart.
- Staleness is mechanically detectable. `backfill` is the only repair
  tool and the only source of truth about "is the embedding
  current?".

**Negative / risks:**

- `pgvector` becomes a hard dependency. Neon supports it, but any
  future move to a Postgres that does not would require a swap.
- OpenAI becomes a hard dependency of the registration write path,
  not just the agent layer. Bootstrap runs offline are no longer
  possible without an embedding API. Mitigation: `backfill` can fill
  embeddings later if writes were performed with the embedding API
  unreachable — at the cost of a temporary search-recall gap.
- Embedding-input composition is a versioned coupling. Changing what
  goes into the composed text invalidates every existing embedding.
  This is the design's intended behaviour, but it means
  `compose_*_embedding_input` functions must be treated as
  semi-stable interfaces with intentional version bumps, not
  refactored casually.
- The MCP read surface now includes a tool whose result quality is
  probabilistic, not deterministic. Reviewers and tests must account
  for top-K candidates being approximate, not authoritative.

**Out of scope for this ADR:**

- The `check_db` node, its prompt, its routing logic. Ratified in
  ADR 0019.
- Re-evaluation of which tables are embedded. Adding any further
  table to the embedded set is a new ADR.
- The supersede-execution mechanics (how a retiring series is
  marked). Tracked separately under governance.
