# ADR 0007 — Subnational regions as country-scoped grouping geographies

**Status:** Accepted

**Date:** 2026-06-08

## Context

The geography model already distinguishes:

- administrative units within a country (`subnational`)
- cross-country aggregates (`region`)
- membership-based groupings (`bloc`)

That leaves a gap for country-scoped grouping geographies such as Japan's
`chiho` regions (`Kanto`, `Chubu`) or US groupings like `Midwest`. These are
real analysis surfaces, but they are not administrative children in the same
sense as prefectures or states, and a country can have multiple valid grouping
schemes at once.

The previous documentation defined `parent_geography_id` as strict
administrative containment only. That is too narrow once country-scoped
grouping geographies exist.

## Decision

- **Add `subnational_region` as a first-class `GeographyType`.**
- **`subnational` remains the administrative subdivision type.** Examples:
  prefectures, states, provinces. Its `parent_geography_id` points to the
  parent country.
- **`subnational_region` represents a country-scoped grouping geography.**
  Examples: `Kanto`, `Tohoku`, `Midwest`. Its `parent_geography_id` points to
  the country it belongs to.
- **Memberships from subnationals into subnational regions live in
  `geography_memberships`.** These memberships are optional and need not be
  exhaustive, because a country may support multiple overlapping grouping
  schemes and we do not want one hard-coded tree.
- **`region` remains reserved for cross-country or supra-national aggregates.**
  Examples: `EAS`, `MEA`.
- **`parent_geography_id` becomes a country anchor for two geography types:**
  `subnational` and `subnational_region`. It is not used to force a single
  grouping hierarchy below the country level.

## Consequences

**Positive:**
- We can represent country-scoped analytical regions without overloading
  `region` or pretending they are administrative units.
- The model stays flexible when multiple grouping schemes exist for the same
  country.
- Membership lineage remains explicit in `geography_memberships`, where it can
  vary over time or by curation choice.

**Negative:**
- `parent_geography_id` is no longer "strict administrative containment only."
  Future readers need the glossary and schema comments to understand the new
  meaning precisely.
- Seed curation gets broader: if we add subnational regions later, we may also
  need curated membership mappings for some countries.

## Alternatives considered

- **Use `region` for both country-scoped and cross-country aggregates.**
  Rejected because it collapses two materially different concepts and makes
  geography filters ambiguous.
- **Force each subnational to point at one subnational region.** Rejected
  because countries can have multiple valid overlapping grouping schemes.
- **Model country-scoped groups as `bloc`.** Rejected because blocs are
  membership-based political/economic groupings, not country-anchored internal
  geography surfaces.
- **Do nothing and represent only subnationals.** Rejected because the missing
  concept is real and analysis-facing.
