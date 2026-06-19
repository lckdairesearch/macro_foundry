# ADR 0025 — Collapse concept / indicator / tag into a category tree

**Status:** Accepted

**Date:** 2026-06-17

Supersedes [ADR 0022](0022-concept-grained-topical-tags.md). Substantially
reverses [ADR 0021](0021-rename-series-family-to-indicator.md) (indicator ceases
to be a stored entity) and the indicator-grain embedding in
[ADR 0020](0020-catalog-embeddings-for-semantic-search.md). Extends
[ADR 0010](0010-request-level-ingestion-and-series-hierarchy.md) (the canonical
series hierarchy is kept; a provider-side grouping layer is added beside it).

The full proposed schema delta lives in `docs/schema/db_er_v8_proposal.txt`.

## Context

The conceptual spine `concept → indicator → indicator_variants → series`, plus a
separate topical `tags` / `concept_tags` taxonomy, is hard to hold in the head.
Four tables encode three closely related ideas (a geography-neutral idea, its
per-geography instantiation, and the membership of methodological variants), and
a fifth pair encodes a flat subject taxonomy that overlaps the first in spirit
but not in structure. Operators and agents conflate them, which CONTEXT.md's
glossary exists to paper over.

Two facts make a structural simplification cheap right now:

- **The catalog is regenerable.** `seed/data/` seeds only geographies,
  memberships, providers, and tags. Concepts, indicators, and variants are
  *generated* by `bootstrap/fred_us_macro.py` and `services/registration.py`, so
  changing their shape is a drop-and-rebootstrap, not a data migration — the
  same near-zero-cost workflow ADR 0022 relied on.
- **Topic and identity are two views of one tree.** A subject taxonomy
  (`PRICES → CONSUMER_PRICES`) and an economic idea (`CPI_ALL_ITEMS`) are the
  same kind of thing at different depths. They do not need separate tables.

Two browse taxonomies were used as source material for the top levels: the Hong
Kong Census & Statistics Department subject tree and Eurostat's statistical
themes, merged with macrodb's existing 10 categories.

## Decision

### 1. One `categories` tree replaces five tables

Collapse `concepts`, `indicators`, `indicator_variants`, `tags`, and
`concept_tags` into a single `categories` table with a `kind` discriminator:

- `kind=topic` — a browse/navigation node (`PRICES`, `CONSUMER_PRICES`). Not
  attachable by a series.
- `kind=concept` — an attachable economic idea (`CPI_ALL_ITEMS`). This is the
  old `concept` grain, and it carries the embedding that lived on `concepts`.

The derived equivalents of the removed entities:

- **indicator** (`US_CPI`) → the *query* `(category_id, geography_id)`. Not a
  stored row. The indicator-grain embedding and free-text description are
  retired.
- **indicator_variant** → `series.is_default` plus the methodology columns
  already on `series`. The free-text `label` folds into `series.name` /
  `series.description`.
- **topic** of a series → the chain of ancestors walked up from its category.

### 2. Strict tree, kept in an adjacency table

The parent/child relation lives in its own `category_edges (parent_category_id,
child_category_id, sort_order)` table rather than a self-FK column — uniform
with macrodb's other membership tables, and edges can carry sibling ordering.
`UNIQUE(child_category_id)` enforces a single parent per node, i.e. a strict
tree. Depth ≤ 3 is a curation convention, not a constraint. A future DAG is one
dropped constraint away, but is explicitly *not* adopted now (see Alternatives).

### 3. Series attaches to its most-specific concept node

`series.category_id` is a **nullable** FK to `categories.id` — the lowest
matchable node. Nullable is deliberate: a draft or deliberately-unclassified
series is allowed. The rule "a series attaches only to a `kind=concept` node,
never a `topic` bucket" is enforced at the **application layer** (Pydantic +
service validation), not the database. Tightening this to a DB constraint later
is a cheap backfill-and-validate pass; loosening a DB constraint is not — so the
looser option is chosen first.

### 4. Provider grouping: generic `source_groups`, canonical hierarchy retained

`series_hierarchy_edges` is kept unchanged as the provider-neutral, canonical
analytical decomposition. Beside it, add a provider-side publication layer:

- `source_groups` — typed (`release | table | dataset | dashboard | other`),
  self-nesting (`parent_group_id`), owned by a `provider_catalog`.
- `source_group_members` — links **`series_source`** (the provider's
  representation), with `row_label` and `sort_order`.

Members are `series_sources` because a published table is a provider artifact;
the same canonical series carried by two providers appears in each provider's own
group. A `series_source` may belong to many groups, so it is not fixed to one
table. Indentation is derived by intersecting membership with
`series_hierarchy_edges`; no per-member parent pointer is stored.

### 5. Reads use recursive CTEs

Hierarchy reads ("all series under `PRICES`", "topic of this series") use
`WITH RECURSIVE` over `category_edges`. With depth ≤ 3 this is trivially cheap. A
closure table is a later swap if category-filtered reads ever become a measured
bottleneck.

### 6. Deferred, additive

- **`series_collections`** — a canonical-side, user-curated, cross-provider
  grouping whose members are canonical `series`. Kept separate from
  `source_groups` (opposite sides of the canonical-vs-provider seam; unifying
  would force a polymorphic member FK or lose provider fidelity). Not built until
  a curation need is real; shared structure can be an ORM mixin.
- **Graph database** (Neo4j / similar) — deferred. pgvector embeddings already
  cover semantic linkage; adjacency tables are traversable with recursive CTEs;
  a graph store would at best be a derived read-model, never a second source of
  truth.

## Consequences

- **Migration is a drop-and-rebootstrap**, not a data move. Workflow: accept this
  ADR → update `db_er.txt` to V8 → migration dropping the five tables and
  creating `categories`, `category_edges`, `source_groups`,
  `source_group_members`, plus `series.category_id` / `series.is_default` →
  align models, schemas, API, admin, seed, bootstrap → update tests → reset,
  reseed, rebootstrap.
- **What is lost, accepted explicitly:** the indicator grain as an addressable,
  embeddable, describable entity; and ADR 0022's topical *overlap* (a strict
  tree gives each concept exactly one topical home).
- **What is preserved:** cross-geography comparison (concept node is
  geography-neutral; series carry geography), the default-reading concept
  (`is_default`), per-series methodology, the canonical decomposition hierarchy,
  and one source of truth per fact (topic / decomposition / publication each
  owned by exactly one relation).
- **Downstream code:** `backend/api/series.py`'s tag flattening,
  `change_proposal_items.target_type` enum (drop `concepts | indicators | tags |
  indicator_variants`, add `categories | source_groups`), CONTEXT.md glossary,
  and `architecture.md` all move with the slice.
- **Integrity now rests on node-kind discipline** rather than table separation.
  In V7 a series structurally could not point at a tag; in V8 the concept/topic
  wall is an app-layer rule. This is the deliberate price of the collapse.

## Alternatives considered

- **Keep the V7 spine, fix only the docs.** Rejected: the confusion is
  structural, and the regeneration window makes a real fix cheap now and costly
  later.
- **Half-collapse — keep a thin `indicators` table.** Rejected for this ADR: the
  indicator grain's only unique payload was an embedding and a description, and
  the operator accepted losing them. Re-introduce a thin `(category, geography)`
  annotation table under its own ADR if a real need appears.
- **DAG instead of a strict tree.** Rejected now: multiple parents reintroduce
  "which parent is canonical", the exact single-source-of-truth ambiguity the
  tree avoids. Adopt later only against a concrete cross-listing need.
- **Unify `source_groups` and `series_collections`.** Rejected: they group
  different member types (`series_source` vs `series`) across the
  canonical-vs-provider seam; one table forces a polymorphic FK or loses
  provider fidelity.
- **Enforce concept-only attachment with a composite-FK trick.** Considered and
  downgraded to app-layer validation, consistent with the operator's liberal
  stance and the cheaper tighten-later direction.
- **Group user collections by `series_source`.** Rejected: would duplicate one
  logical series once per provider, the duplication the canonical model exists to
  avoid.
