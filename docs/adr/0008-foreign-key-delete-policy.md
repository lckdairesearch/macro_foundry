# ADR 0008 — Foreign key delete policy

**Status:** Accepted

**Date:** 2026-06-08

## Context

Phase 5 introduces the full SQLAlchemy model graph and Phase 6 turns that graph
into Alembic migrations. The canonical V3 schema defines the foreign-key graph,
but it did not specify `ON DELETE` behavior for each edge.

That left a real ambiguity:

- some relationships are pure membership rows and should clean themselves up
  when the owning row is deleted
- some rows are canonical curated entities and should not disappear because an
  upstream row was deleted
- some rows are lineage or audit history (`observations`, run logs, governance
  proposals) and silent cascades would destroy information we expect to keep

Relying on Postgres defaults (`NO ACTION`) would make the policy implicit and
easy to miss in review. We need an explicit, documented rule set before the
models and migrations land.

## Decision

- **Every foreign key in V3 declares an explicit `ondelete` policy.** Do not
  rely on database defaults for delete behavior.
- **`RESTRICT` is the default.** Use it for canonical entities, self-references,
  hierarchy edges, lineage-bearing rows, and audit/history rows.
- **`CASCADE` is used only for rows that are purely owned by the parent and have
  no standalone meaning.**
- **Do not use `SET NULL` in the Phase 5/6 schema.** If a replacement,
  supersession, lineage, or audit link exists, deleting the referenced row
  should require an explicit repair first rather than silently erasing the link.

Canonical `ON DELETE` map:

- `geographies.parent_geography_id` → `RESTRICT`
- `geography_memberships.member_geography_id` → `CASCADE`
- `geography_memberships.group_geography_id` → `CASCADE`
- `series.geography_id` → `RESTRICT`
- `series.replaced_by_series_id` → `RESTRICT`
- `series_families.concept_id` → `RESTRICT`
- `series_families.geography_id` → `RESTRICT`
- `provider_catalogs.provider_id` → `RESTRICT`
- `series_tags.series_id` → `CASCADE`
- `series_tags.tag_id` → `CASCADE`
- `series_family_members.family_id` → `CASCADE`
- `series_family_members.series_id` → `CASCADE`
- `series_hierarchy_edges.parent_series_id` → `RESTRICT`
- `series_hierarchy_edges.child_series_id` → `RESTRICT`
- `series_sources.provider_catalog_id` → `RESTRICT`
- `series_sources.series_id` → `CASCADE`
- `ingestion_feed_members.ingestion_feed_id` → `CASCADE`
- `ingestion_feed_members.series_source_id` → `CASCADE`
- `derived_series.series_id` → `CASCADE`
- `derivation_inputs.derived_series_id` → `CASCADE`
- `derivation_inputs.input_series_id` → `RESTRICT`
- `ingestion_run_logs.ingestion_feed_id` → `RESTRICT`
- `computation_run_logs.derived_series_id` → `RESTRICT`
- `observations.series_id` → `RESTRICT`
- `observations.ingestion_run_log_id` → `RESTRICT`
- `observations.computation_run_log_id` → `RESTRICT`
- `change_proposals.superseded_by_proposal_id` → `RESTRICT`
- `change_proposal_items.proposal_id` → `CASCADE`

## Consequences

**Positive:**
- Reviewers can check every FK in Phase 5 models and Phase 6 migrations against
  one explicit policy.
- Core curated entities and historical records are protected from accidental
  deep deletes.
- Pure junction or owned-extension rows still clean themselves up automatically,
  so scratch records and local admin mistakes do not leave orphan rows behind.
- The presence of `DELETE` endpoints for simple tables remains useful: unreferenced
  rows can still be removed, while referenced rows fail loudly instead of causing
  silent data loss.

**Negative:**
- Some deletes will fail until child rows are removed or a relationship is
  cleared explicitly. That is deliberate friction.
- The policy is a bit asymmetric in places. For example, a `series` owns its
  `series_sources`, but a `provider_catalog` does not own them for delete
  purposes. That asymmetry reflects the curation model, not an accident.

## Alternatives considered

- **Leave `ON DELETE` unspecified and accept Postgres defaults.** Rejected
  because the policy would remain implicit and easy to misread in both models
  and migrations.
- **Default to `CASCADE` for most child rows.** Rejected because macrodb is a
  preservation-oriented curated data layer; broad cascades make accidental data
  loss too easy.
- **Use `SET NULL` for replacement, supersession, and lineage links.** Rejected
  because it hides integrity problems instead of forcing an explicit repair.
- **Soft-delete everything and avoid hard deletes entirely.** Rejected for this
  phase. The schema already distinguishes where retirement metadata belongs via
  `is_active`; forcing soft-delete semantics onto every table would be a broader
  architectural change than needed here.
