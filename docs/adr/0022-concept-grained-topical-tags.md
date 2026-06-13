# ADR 0022 — Concept-grained topical tags

**Status:** Proposed

**Date:** 2026-06-13

## Context

The schema models tags as a free-form taxonomy attached to `series` through a
`series_tags` M:N junction (`db_er.txt:159`). In practice the seeded tag
vocabulary is not free-form at all — it is a fixed set of **topical
subject-area categories** (`seed/data/tags.py`): `national_accounts`,
`prices`, `labor_population`, `money_banking_finance`,
`production_business_activity`, `international`, `housing`. These resemble the
top-level subject trees of FRED and the IMF IFS, not per-series labels.

Three problems follow from attaching a topical taxonomy at the `series` grain:

- **Wrong grain.** A topic is a property of the economic *idea*, i.e. the
  `concept`. Every series under `CPI` is `prices`; every series under `GDP` is
  `national_accounts`. The topic does not vary across geography or methodology
  variant, so it should not be stored per series.
- **Redundancy and inconsistency risk.** Series-grain tagging repeats the same
  assignment across every series sharing a concept, and admits the bug where
  `US CPI` is tagged `prices` but `JP CPI` is not. Concept-grain tagging makes
  that class of inconsistency structurally impossible; series inherit the topic
  transitively via `indicator_variants → indicators.concept_id`.
- **The feature is currently inert.** Nothing constructs a `SeriesTag` row —
  not the seed (it seeds only the 7 `Tag` names), not the FRED bootstrap, not
  the onboarding agent. There is no data to migrate, so the grain can be
  corrected at near-zero cost now and at rising cost later.

A secondary inconsistency: `tags` is the only curated identity-bearing table
that keys on `name` alone. `geographies`, `concepts`, `series`, and
`indicators` all carry a canonical `code` (the user-facing key; UUID is
internal — see `CONTEXT.md`). With `name` doing double duty as both key and
display string, a category cannot be reworded without breaking its key.

## Decision

### 1. Regrain tags from `series` to `concept`

Replace the `series_tags` junction with `concept_tags (concept_id, tag_id)`,
composite PK, both FKs `ON DELETE CASCADE`. Drop `Series.series_tags`; add
`Concept.concept_tags`. A series' topical tags are derived transitively through
its family's concept, not stored on the series. `series_tags` is removed
entirely rather than kept "just in case" — when a genuinely series-grain,
non-topical tag appears (e.g. `leading_indicator`), it is re-introduced under
its own ADR.

### 2. Give `tags` a `code` + `name`, modeled like `concepts`

```
tags {
  id    uuid pk
  code  string unique   // canonical slug, UPPERCASE
  name  string          // human display label
  created_at timestamp
  updated_at timestamp
}
```

`code` becomes the unique natural key; `name` is free display text. Tags follow
the `concepts` pattern (internal, curated, no external standard) — so `code` +
`name`, and **no** `code_standard` field (that is geography-specific).

### 3. Replace the 7 categories with a 10-category taxonomy

| code | name |
|---|---|
| `PRICES` | Prices |
| `MONETARY_BANKING` | Monetary and Banking Variables |
| `POPULATION_LABOR` | Population and Labor Market |
| `PRODUCTION_BUSINESS_ACTIVITY` | Production and Business Activity |
| `RETAIL_CONSUMPTION` | Retail and Consumption |
| `NATIONAL_ACCOUNTS` | National Accounts |
| `GOVERNMENT_FISCAL` | Government and Fiscal |
| `INTERNATIONAL` | International |
| `FINANCIAL_INDICATORS` | Financial Indicators |
| `OTHER` | Others |

Notable choices:

- **No `housing` category.** Neither FRED (nests Housing under Production &
  Business Activity) nor IMF IFS (no housing top-level) treats housing as a
  top-level subject. House-price indices route to `PRICES`, mortgages to
  `MONETARY_BANKING`, construction to `PRODUCTION_BUSINESS_ACTIVITY`. M:N still
  allows a series' concept to carry several of these.
- **`GOVERNMENT_FISCAL` is government operations**, distinct from
  `NATIONAL_ACCOUNTS`: revenue, expenditure, deficit/surplus, public debt stock,
  and tax data. The IMF treats this as a standalone domain (Government Finance
  Statistics). Government consumption *within GDP* stays `NATIONAL_ACCOUNTS`; a
  sovereign bond *yield* is `FINANCIAL_INDICATORS` (the market price of debt),
  while the debt *stock* and fiscal position are `GOVERNMENT_FISCAL`. Overlaps
  are absorbed by M:N.
- **`INTERNATIONAL` is the external sector**, not only trade: balance of
  payments, current account, reserves, and exchange rates land here.
- **`MONETARY_BANKING` vs `FINANCIAL_INDICATORS` boundary:** monetary/banking =
  policy-set or banking-system quantities (money supply, policy rate, bank
  credit, reserves); financial = market-determined asset prices (equity
  indices, bond yields, spreads, FX, volatility). Overlaps (e.g. bond yields)
  are absorbed by M:N and need not be agonised over.
- **`OTHER`** is a deliberate catch-all. A large `OTHER` population is a signal
  that the taxonomy is missing a category, to be reviewed, not a normal state.

### 4. Codify the `code` casing convention as governance

The existing `code` columns share an unwritten convention, now made explicit in
`CONTEXT.md`:

> Codes are **UPPERCASE**. Internal, curated codes use **SCREAMING_SNAKE**
> (`CPI`, `GDP`, `UNEMPLOYMENT_RATE`, `US_CPI`, `NATIONAL_ACCOUNTS`). Codes
> adopted from an external standard follow that standard's own format
> (ISO 3166 hyphenated for `geographies`: `US-CA`, `JP-01`). `code` is `UNIQUE`
> within its table and is the user-facing key; the UUID is internal.

This rule is **convention-only**, consistent with current practice: it is
documented and seeded-against, but **not** enforced by a Pydantic validator or
CHECK constraint. Mechanically enforcing code format is a legitimate but
separate, schema-wide decision (a shared annotated `Code` type across all four
tables) and is explicitly out of scope here — tags must not become the lone
table with a format validator.

## Consequences

- **No data migration.** Because `series_tags` is unpopulated, the change is a
  drop-and-recreate. Workflow: update `db_er.txt` (V3 source of truth) → add
  incremental migration `0013_concept_tags` (drop `series_tags`, create
  `concept_tags`, add `tags.code`) → align models/schemas/API/admin/seed →
  update tests → reset, reseed, rebootstrap.
- **One non-trivial code change:** `backend/api/series.py` currently flattens
  `Series.series_tags → tag` onto `SeriesReadDetail.tags`. It must instead load
  the topic transitively (`indicator_variant → indicator → concept → concept_tags`), a
  deeper `selectinload` join. Everything else (`models/tag.py`,
  `models/series.py`, `models/concept.py`, `schemas/tag.py`, the
  `series_tags`→`concept_tags` router, `admin/views/tag.py`, `seed/data/tags.py`
  as `(code, name)` tuples, `seed/runners/tags.py` conflicting on `code`) is a
  mechanical regrain/rename.
- **Doc updates:** `CONTEXT.md` gains the casing rule and a concept-grained
  tag note; `architecture.md:337` changes its cited tag natural key from
  `tags.name` to `tags.code`.
- **Populating links is still owed.** Regraining does not make tags *do*
  anything by itself; nothing populates the junction at either grain today. The
  concept grain makes population tractable — a small curated seed mapping
  `concept_code → [tag_code]` — which is a far smaller surface than per-series
  assignment. That seed is follow-on work, not part of this ADR.

## Alternatives considered

- **Keep tags at the `series` grain.** Rejected: stores a concept-intrinsic
  property at the wrong grain, with redundancy and the cross-geography
  inconsistency bug the regrain eliminates.
- **Collapse tags to a single `category` FK on the row.** Rejected: the
  topical categories genuinely overlap (a house-price index is `PRICES` and
  arguably `PRODUCTION_BUSINESS_ACTIVITY`), so the relationship is truly M:N.
- **Keep both `series_tags` and add `concept_tags`.** Rejected as premature: no
  series-grain, non-topical tag exists today. Re-introduce `series_tags` under
  its own ADR when one does.
- **Keep `name`-only keying for tags.** Rejected: leaves tags as the lone
  identity table without a stable machine key, and conflates key with display.
- **Enforce code casing with a validator now.** Deferred: enforcement is a
  schema-wide concern across all `code` columns, not a tags-only addition.
