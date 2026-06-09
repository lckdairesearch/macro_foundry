# Series Catalog Governance

This document governs how canonical macrodb series are named and how future
workers should decide whether something is a concept, a series family, or a
series variant.

It is intentionally narrow. This is not an ingestion spec. It is the naming and
catalog policy that sits on top of the glossary in `CONTEXT.md`.

## Purpose

The `series.code` field is a canonical internal identifier. It is not a provider
ticker namespace. The goal of this policy is to keep series identity stable even
when the same series is sourced from different providers or redistributors.

## Governing rules

1. `series.code` is semantic and provider-agnostic.
2. Provider tickers belong in `series_sources.external_code`.
3. A concept is geography-neutral.
4. A series family is exactly one concept plus one geography.
5. Methodological differences between sibling series in one family are modeled
   as series variants, not new concepts, unless the underlying economic idea is
   genuinely different.
6. A code should be readable by both humans and agents without consulting a
   provider manual.

## Canonical code grammar

Canonical `series.code` values use this ordered grammar:

`<geo>_<concept>_<variant?>_<freq>_<sa>_<measure>`

Slot definitions:

- `<geo>`: internal geography shorthand such as `US`
- `<concept>`: canonical concept code such as `GDP` or `CPI`
- `<variant?>`: optional methodological qualifier such as `NOMINAL`, `REAL`,
  `HEADLINE`, or `CORE`. This slot may itself contain multiple underscore-delimited
  tokens when one qualifier is not enough.
- `<freq>`: frequency token such as `Q` or `M`
- `<sa>`: seasonal-adjustment token such as `SAAR`, `SA`, or `NSA`
- `<measure>`:
  - raw levels use `LEVEL`
  - derived year-over-year growth uses `YOY`

Rules:

- Omit the variant slot only when the family has a single obvious canonical
  variant.
- Keep slots in this order. Do not invent ad hoc reorderings.
- Prefer short, stable tokens over prose.
- Compound variants are allowed. When a series needs more than one qualifier,
  keep them together inside the variant slot using underscore-delimited tokens.
  Example: `CORE_1P_HH`.
- Prefer explicit separated tokens over compressed blobs. Use
  `CORE_1P_HH`, not `CORE1PHH`.
- Do not include provider names or provider tickers in the canonical code.

## Parsing expectations

`series.code` should remain readable and reasonably machine-friendly, but code
parsing must respect the actual domain model.

Parsing guidance:

- treat `<freq>_<sa>_<measure>` as the fixed suffix and parse that from the right
- treat `<geo>` as the leftmost token
- resolve `<concept>` by matching the longest known `concept.code`
- treat any tokens between the resolved concept and the fixed suffix as the
  variant slot

Do not assume the middle of the code is "variant only." Concept codes can
contain underscores, such as `CURRENT_ACCOUNT_BALANCE` or
`HOUSEHOLD_CONSUMPTION`.

Machine parsing of `series.code` is a convenience, not the primary source of
truth. For structured work, prefer the explicit series columns for frequency,
seasonal adjustment, measure, and related methodology.

## Concept vs family vs variant

Use this decision rule:

- New concept: only when the underlying geography-neutral economic idea is
  different.
- New family: when the same concept needs a geography-specific grouping.
- New series variant inside a family: when the economic idea is the same but
  methodology differs, such as nominal vs real, headline vs core, or SA vs NSA.

Examples:

- `GDP` and `real GDP` are one concept (`GDP`) with separate variants in one
  geography family.
- Headline CPI and core CPI are one concept (`CPI`) with separate variants in
  one geography family.
- Household-basis CPI variants such as one-person and two-or-more-person
  baskets remain one `CPI` concept and one `JP_CPI` family; they become
  separate sibling series with different variants.
- A provider redistributor copy of a series is not a new concept and not a new
  canonical series code; it is a new `series_source`.

For compound variant cases, use explicit tokens in the code and a readable
label in the family membership row. Example pair:

- `JP_CPI_CORE_1P_HH_M_NSA_LEVEL`
- `JP_CPI_CORE_2PPLUS_HH_M_NSA_LEVEL`

Matching `series_family_members.variant` values might be:

- `Core, one-person household basket`
- `Core, two-or-more-person household basket`

## Provider mapping rule

Canonical identity and provider mapping must stay separate:

- canonical identity: `series.code`
- provider mapping: `series_sources.external_code`

This means:

- FRED `GDP` maps to a semantic canonical code such as
  `US_GDP_NOMINAL_Q_SAAR_LEVEL`
- FRED `GDPC1` maps to a semantic canonical code such as
  `US_GDP_REAL_Q_SAAR_LEVEL`
- the FRED ticker never becomes the canonical code just because it is the first
  provider wired up

## Naming examples for the first FRED preset

The first curated FRED bootstrap preset uses:

Concepts:

- `GDP`
- `CPI`

Series families:

- `US_GDP`
- `US_CPI`

Raw ingested series:

- `US_GDP_NOMINAL_Q_SAAR_LEVEL`
- `US_GDP_REAL_Q_SAAR_LEVEL`
- `US_CPI_HEADLINE_M_NSA_LEVEL`
- `US_CPI_CORE_M_SA_LEVEL`

Derived series:

- `US_GDP_NOMINAL_Q_SAAR_YOY`
- `US_GDP_REAL_Q_SAAR_YOY`
- `US_CPI_HEADLINE_M_NSA_YOY`
- `US_CPI_CORE_M_SA_YOY`

Provider mappings for the first preset:

- `GDP` -> `US_GDP_NOMINAL_Q_SAAR_LEVEL`
- `GDPC1` -> `US_GDP_REAL_Q_SAAR_LEVEL`
- `CPIAUCNS` -> `US_CPI_HEADLINE_M_NSA_LEVEL`
- `CPILFESL` -> `US_CPI_CORE_M_SA_LEVEL`

## Human-readable naming expectations

Use descriptive `series.name` values alongside the canonical code. The code
should stay compact; the name should stay readable.

Examples:

- `United States Gross Domestic Product, Nominal Level`
- `United States Real Gross Domestic Product, YoY`
- `United States CPI Headline, Level`
- `United States CPI Core, YoY`

## What not to do

Do not:

- reuse provider tickers as canonical codes by default
- create a new concept just because the provider exposes a new methodological
  variant
- encode provenance in the canonical code
- change slot order from one family to another
- invent one-off abbreviations that are not obvious from the surrounding family
- rely on a naive fixed-position parser that assumes concept codes never contain
  underscores

## Change discipline

When adding new series families or expanding this grammar:

1. Check `CONTEXT.md` first to confirm the concept/family distinction.
2. Follow this document unless there is a strong reason not to.
3. If the naming change would be surprising, hard to reverse, or likely to
   become precedent outside one narrow case, discuss it before implementing.
