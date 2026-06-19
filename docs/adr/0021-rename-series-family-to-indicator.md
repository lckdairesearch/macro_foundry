# ADR 0021 — Rename `series_family` to `indicator`

**Status:** Accepted (substantially reversed by [ADR 0025](0025-collapse-concept-indicator-tag-into-category-tree.md) — indicator is no longer a stored entity)

**Date:** 2026-06-13

## Context

The catalog's conceptual layer is a four-rung stack: `concept` →
`series_family` → `series` → `observation`. A `series_family` groups one
`concept` and one `geography`; a `series` is one methodological realization
within that family; and the association row `series_family_members` carries the
`variant` label and the `is_primary` flag that mark how each series differs from
its siblings and which one is the family's default reading.

Two of these rung names are home-grown. In measurement-theory and official-
statistics vocabulary, the thing a `series_family` actually is — an
operationalized, unit-bearing measure of a geography-neutral `concept` for one
geography — is an **indicator**. This is precisely the word the World Bank WDI,
OECD, IMF, and SDMX-speaking publishers use for their catalog entries, and
every provider this system ingests from speaks that dialect. The standard term
sits unused while `series_family` does its job in a clunkier, more idiosyncratic
register.

Three forces motivate aligning the names now rather than later.

- **Domain-language alignment.** CLAUDE.md and CONTEXT.md make the project's
  domain glossary load-bearing for both humans and agents. The schema should
  speak the same language as the economists and publishers it models. The
  measurement-theory stack reads cleanly as `concept → indicator →
  indicator_variant → observation`.
- **Internal consistency with already-canonized terms.** The association row's
  payload is variant semantics, not membership bookkeeping. `variant` is already
  a first-class glossary term (CONTEXT.md), and `is_primary` is the
  implementation of the already-defined **default variant** concept. Naming the
  column `is_default` makes the schema state out loud what the glossary already
  asserts.
- **Cost of delay.** The longer the home-grown names persist, the more code,
  prompts, MCP tool contracts, governance audit values, and docs accrete
  around them. The rename is cheapest now, before further growth.

The `concept` rung is deliberately **not** renamed. "Concept" is the term SDMX
uses as a first-class component, which buys interoperability legibility with
every upstream source. The candidate replacements fail: "construct" implies
latency (correct for `INFLATION`, wrong for directly-counted quantities like
`EXPORTS` or `GOVERNMENT_DEBT`), and "variable" is both overloaded and drifts
toward the operationalized, series-level grain. Concept stays.

## Decision

Rename the middle two rungs and their distinguishing columns to align canonical
schema names with measurement-theory vocabulary. The `concept` rung,
`series`, and `observation` are unchanged.

| Old | New |
|---|---|
| table `series_families` | `indicators` |
| table `series_family_members` | `indicator_variants` |
| column `series_family_members.family_id` | `indicator_variants.indicator_id` |
| column `series_family_members.variant` | `indicator_variants.label` |
| column `series_family_members.is_primary` | `indicator_variants.is_default` |
| class `SeriesFamily` | `Indicator` |
| class `SeriesFamilyMember` | `IndicatorVariant` |

The resulting stack is `concept → indicator → indicator_variant →
observation`, where an indicator is the operationalized measure of a concept for
one geography, and each indicator-variant row is a methodological variant of
that indicator (nominal/real, headline/core, SA/NSA), exactly one of which is
the `is_default` baseline reading.

**Why `indicator_variants` and not `indicator_members`.** The association table
is strictly an edge, and a purist would name an edge for membership. But variant
identity only *exists* relative to siblings — a lone series is not "core" except
in contrast to "headline" — and the association row is precisely where that
contrast, and the default-variant choice, is asserted relative to the indicator.
The row therefore legitimately owns the variant vocabulary. `indicator_members`
is the conservative fallback if schema-purity is later weighted over readability.

**No backwards-compatibility shims.** Per `docs/code_standards.md`, the rename is
applied atomically rather than staged behind temporary aliases or re-exports.
The data is carried forward by an in-place migration (`ALTER TABLE ... RENAME`,
`RENAME COLUMN`, constraint renames), not drop-and-recreate, so existing rows and
embeddings are preserved.

This is a **pure rename**: no change to series identity, the publication
boundary, catalog grammar, or any semantic behavior. `docs/schema/db_er.txt`
remains the source of truth and is updated to the new names as part of this
decision; SQLAlchemy models, the Alembic migration, Pydantic schemas, and tests
must agree with it.

## Consequences

**Positive.**

- Canonical schema names match how economists and every upstream publisher
  (WDI, OECD, IMF, SDMX) already talk, improving both human and agent
  navigability.
- `is_default` ties the column directly to the existing "default variant"
  governance term, removing a generic junction-table name that obscured its
  meaning.
- The measurement-theory layering becomes explicit and self-documenting in the
  schema itself: `concept → indicator → indicator_variant → observation`.

**Negative / cost.**

- A broad rename with several distinct blast radii, sequenced as issues #67–#71:
  the core DB + models + internal code (#68), the governance stored-enum values
  (#69), the external name-contracts (#70), and the documentation sweep (#71).
- The governance `TargetType` / `proposal_type` values (`series_families`,
  `series_family_members`, `add_family`) are **persisted strings** under named
  CHECK constraints (per ADR 0005). Renaming them requires a CHECK-widen +
  data-migration following the ADR 0014 pattern, on a different table from the
  core rename.
- The MCP tool names (`lookup_family`, `search_series_families`) and REST URL
  prefixes (`/series-families`, `/series-family-members`) are external contracts;
  renaming them changes the agent-facing and HTTP surfaces and must update the
  onboarding prompts in lockstep.
- The retired `src/macro_foundry/agent` directory is explicitly excluded and not
  touched.

## Alternatives considered

- **Rename `concept` as well (to "construct" or "variable").** Rejected.
  "Construct" implies an unobservable latent quantity, which mis-describes the
  majority of concepts that are directly counted or defined (exports, debt,
  population). "Variable" is overloaded and drifts toward the operationalized
  grain. "Concept" is SDMX-aligned and stays.
- **Leave `series_family` as-is.** Rejected. The term is idiosyncratic and
  misaligned with the standard vocabulary, and the misalignment compounds as the
  catalog grows. The standard term "indicator" is both clearer and free.
- **`indicator_members` for the association table.** Rejected as the primary
  choice (kept as fallback). It names the plumbing rather than the meaning; the
  row's payload is variant + default-variant semantics, which `indicator_variants`
  states directly.
- **Keep `variant` / `is_primary` column names after the table rename.**
  Rejected. `indicator_variants.variant` is redundant, and `is_primary` is a
  generic junction-table word; `label` and `is_default` align with the glossary.
- **Stage the rename behind compatibility aliases.** Rejected per
  `docs/code_standards.md`. Aliases would let the rename land in smaller pieces
  but violate the no-shim rule and leave dual vocabulary in the codebase.
- **Fold the governance stored-enum rename into the core migration.** Rejected.
  It touches a different table (`change_proposals` / `change_proposal_items`),
  carries stored-data risk, and is cleanly separable; it is sequenced as its own
  slice (#69) to keep blast radius and the Alembic chain manageable.
