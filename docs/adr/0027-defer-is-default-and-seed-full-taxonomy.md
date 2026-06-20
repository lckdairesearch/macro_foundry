# ADR 0027 — Defer `series.is_default`; seed the full concept taxonomy

**Status:** Accepted

**Date:** 2026-06-20

Amends [ADR 0025 §1](0025-collapse-concept-indicator-tag-into-category-tree.md)
(the `indicator_variant → series.is_default` materialization) and
[ADR 0026 §5 / Consequences](0026-top-level-category-taxonomy-and-concept-naming.md)
(the "seed only the universal concepts, accrete the long tail" stance). Both are
operator-review adjustments to the just-landed V8 catalog (issues #78–#85); neither
changes the `categories` schema shape, the strict single-parent tree, or the ≤3
depth convention.

## Context

Issues #78–#85 collapsed `concept / indicator / tag` into one `categories` tree,
attached series to `kind=concept` nodes, remapped the FRED bootstrap, and
reconciled the docs. Reviewing that landed surface surfaced two decisions.

### 1. `series.is_default` carried no weight

ADR 0025 §1 mapped the V7 `indicator_variants.is_default` to a `series.is_default`
boolean — "the default reading within `(category_id, geography_id)`". In practice
it was inert: unenforced (no partial-unique index), absent from the admin surface,
and disambiguating nothing because every `(concept, geography)` slice held a single
series. It marked a real future need (which of several readings is the headline)
that no current data exercises.

### 2. The concept long tail is curated, not emergent

ADR 0026 §5 seeded only the topic skeleton plus ~9 universal concepts and left the
~148-concept long tail to **accrete** at runtime, on the theory that concepts are
generated. But the full 157-concept taxonomy already exists as curated,
human-reviewed, validation-tested content (`docs/schema/category_taxonomy.xlsx`,
94% coverage over 388 real series). Withholding it from the seed bought nothing: it
made bootstrap/onboarding mint concepts that were already designed, and left the
catalog's conceptual vocabulary undiscoverable until series happened to arrive.

## Decision

### 1. Defer `series.is_default`

Drop the `series.is_default` column (migration `0021`). The default-reading marker
returns under its own ADR when a real multi-series `(category_id, geography_id)`
slice needs it — at which point its shape (per-series boolean vs. a curated
pointer) can be chosen against a concrete case. This is the same loose-first,
tighten-later direction ADR 0025 took for concept-only attachment. `category_id`
(added beside it in `0019`) is unaffected.

### 2. Seed the full concept taxonomy

Seed all 243 curated nodes — 15 domains, 71 subdomains, 157 L3 concepts (171
`kind=concept` total) — from the taxonomy workbook, like geographies. The seed
runner stays offline (no OpenAI dependency), so seeded concepts carry **no
embedding**; `macrodb embeddings backfill` (extended to `kind=concept` nodes) is
the repair path that makes concept semantic-search work. Runtime accretion
(`services.registration.register_concept_node`) is retained as the **fallback** for
genuinely novel concepts onboarding discovers that the taxonomy lacks — no longer
the primary path. The ADR 0010 "no placeholder concepts" rule is read as forbidding
*auto-generated* junk nodes, not curated, reviewed reference data.

## Consequences

- Migration `0021` drops `series.is_default`; the model, `SeriesBase`/`SeriesUpdate`
  schemas, the bootstrap spec/payload, and the `list_series` `is_default` filter all
  lose it. `db_er.txt` and CONTEXT.md mark the default reading as deferred.
- The `categories` seed grows from ~95 nodes to 243. `seed/data/categories.py`'s
  `UNIVERSAL_CONCEPTS` becomes `CONCEPTS` (the full L3 tail).
- `embeddings backfill` now embeds concept nodes too; on a fresh seed all 171
  `kind=concept` nodes are stale until one backfill run.
- The FRED bootstrap finds its four concepts pre-seeded instead of minting them;
  the mint path is exercised by `test_concept_accretion` against a synthetic
  non-seeded code.
- **Owed:** an operator `embeddings backfill --target {dev,staging}` run to populate
  the seeded concepts' embeddings (needs a live `OPENAI_API_KEY`).

## Alternatives considered

- **Keep `is_default`, leave it unenforced.** Rejected: a column that disambiguates
  nothing and is invisible to the admin is dead surface; cheaper to re-add when a
  real multi-series slice defines what "default" should mean.
- **Add a partial-unique on `is_default`.** Rejected as premature: it would enforce
  exactly-one-default before any slice needs more than one series.
- **Keep accreting the long tail (ADR 0026 §5 as written).** Rejected: it discards
  finished, validated curation work and hides the conceptual vocabulary until data
  arrives. Accretion still earns its keep for the genuinely-novel case.
- **Embed concepts at seed time.** Rejected: the seed must stay offline and
  deterministic (it runs in tests with no API key); embedding is the backfill's job.
