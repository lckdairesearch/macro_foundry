# ADR 0010 - Request-level ingestion and canonical series hierarchy

**Status:** Accepted

**Date:** 2026-06-09

## Context

The V3 ingestion model attached each `ingestion_feed` directly to one
`series_source`. That was adequate for simple providers such as FRED, where one
request generally maps to one logical provider series.

It breaks down for table-style and tree-style statistical sources. One upstream
request can return a table or decomposition tree that populates several
canonical series. Duplicating the shared request configuration once per output
series would misstate the real execution unit, and hiding the split in runtime
code would make provenance incomplete.

The same sources also reopen canonical decomposition work. Macrodb needs to
answer questions about real parent-child `series` relationships without tying
that answer to one provider's layout, and without inventing hidden canonical
placeholder nodes solely to mirror provider indentation.

## Decision

`ingestion_feed` is a request-level ingestion unit: the runtime configuration
for one upstream request shape or execution unit. It may populate one or more
`series_sources`.

Add `ingestion_feed_member` as the attachment between one request-level feed
and one `series_source`. The member carries the per-series extraction contract,
including `selector_type`, structured `selector_config`, `is_active`, and
optional execution ordering. The common one-request-to-one-series case remains a
feed with one active member.

`ingestion_run_log` remains append-only and feed-level: one row per execution
of a request-level feed. Add `ingestion_run_log_member` for member-level
provenance: one attempted active member inside one feed execution, with status,
row counts, and selector/parsing diagnostics. Observations produced by
ingestion point to the member-level run row, not only to the feed-level run.

`series_source` remains the mapping from one canonical `series` to one provider
representation. Its provider locator fields are descriptive and reviewable, not
the execution unit. `external_code` should become nullable and no longer be the
only extraction locator; `ref_url` should be added as a nullable but strongly
encouraged human-facing source link.

Add a canonical `series` hierarchy as an explicit parent-child structure
between real canonical series. The hierarchy is ragged by default. A grouping
node exists as a canonical `series` only when it is analytically meaningful or
directly published by a source. Parent observations remain stored as published
values even when children exist and even when an aggregation rule is known.
Same-concept hierarchy edges are the default; cross-concept hierarchy proposals
require explicit human review.

Routine ingestion refreshes must not silently mutate hierarchy structure.
Hierarchy changes belong in onboarding, approved repair, or another explicit
metadata workflow.

## Consequences

**Positive:**

- Provenance matches real provider execution: one shared request has one
  feed-level run and member-level outcomes for every attempted logical series.
- Partial shared-request outcomes can be represented without losing detail:
  success, no-op, partial, warning, and failure are visible per member.
- Observations carry member-level provenance, so a stored value points to the
  exact extraction attempt that produced it.
- Clean providers stay simple because the one-member feed remains the baseline
  shape.
- Canonical decomposition questions are answered in the `series` layer, not by
  reverse-engineering provider-specific source trees.
- Hidden canonical placeholder nodes are rejected, keeping the catalog made of
  real analytical or published series.

**Negative:**

- The schema becomes larger: two member tables are added, and observation
  provenance moves from feed-level to member-level run logs.
- Existing FRED bootstrap scaffolding and source-centric ingestion code need to
  be rewritten rather than preserved as architectural anchors.
- The V3 canonical schema, models, schemas, migrations, admin, routes, and tests
  must move together in the implementation slice; updating only one layer would
  create drift.

## Alternatives considered

- **Keep source-centric feeds and duplicate request config.** Rejected because it
  misstates the provider execution unit and makes shared-request provenance
  impossible to audit truthfully.
- **Keep one feed per source but hide fan-out in provider-specific runtime code.**
  Rejected because the database would not know which logical outputs were
  attempted, failed, or no-oped inside a shared request.
- **Make `series_source` the extraction contract.** Rejected because provider
  mapping and request execution are different concepts. Some providers have
  clean external series codes; others need selectors, dimensions, or tree paths.
- **Attach observations only to feed-level run logs.** Rejected because one
  shared feed can produce mixed member outcomes. Member-level provenance is the
  durable audit surface.
- **Create hidden canonical placeholder nodes to fill provider tree gaps.**
  Rejected because macrodb's canonical catalog should contain meaningful or
  published series, not invisible nodes invented to satisfy provider layout.
