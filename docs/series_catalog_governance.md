# Series Catalog Governance

This document governs how canonical macrodb series are named and how future
workers should decide whether something is a concept, an indicator, or a
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
4. An indicator is exactly one concept plus one geography.
5. Methodological differences between sibling series in one indicator are modeled
   as series variants, not new concepts, unless the underlying economic idea is
   genuinely different.
6. A code should be readable by both humans and agents without consulting a
   provider manual.
7. Not every provider-exposed qualifier must appear in the canonical code.
8. An indicator may have a curated default variant whose qualifier is omitted
   from `series.code` when that omission is unlikely to create confusion inside
   the project.
9. If the methodological scope is materially ambiguous, an agent should flag
   the ambiguity and propose rather than create a new canonical series.
10. Once a canonical series has crossed the publication boundary described in
    `CONTEXT.md`, identity corrections are dangerous and should not be applied
    automatically by an agent.

## Canonical code grammar

Canonical `series.code` values use this ordered grammar:

`<geo>_<concept>_<variant?>_<freq>_<sa>_<measure?>`

Slot definitions:

- `<geo>`: internal geography shorthand such as `US`
- `<concept>`: canonical concept code such as `GDP` or `CPI`
- `<variant?>`: optional methodological qualifier such as `NOMINAL`, `REAL`,
  `HEADLINE`, or `CORE`. This slot may itself contain multiple underscore-delimited
  tokens when one qualifier is not enough.
- `<freq>`: frequency token such as `Q` or `M`
- `<sa>`: seasonal-adjustment token such as `SAAR`, `SA`, or `NSA`
- `<measure?>`: omitted for level series; explicit token for derived
  measures, such as `YOY` for year-over-year growth. Level is the default,
  so a code with no trailing measure token denotes a level.

Rules:

- Omit the variant slot only when the indicator has a single obvious canonical
  variant.
- An indicator may also omit a qualifier for its curated default variant when
  the project has intentionally decided that one scope is the baseline reading
  for that indicator.
- Omit the measure slot for level series. Only add a measure token when the
  series is a non-level transformation (for example `YOY`).
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

- the fixed suffix is `<freq>_<sa>` for level series and
  `<freq>_<sa>_<measure>` for non-level measures; parse it from the right
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

## Default variants and omitted qualifiers

Canonical codes should capture distinctions that matter to macrodb's intended
identity, not every peripheral distinction a provider happens to expose.

This means an indicator may define one methodological scope as the default
reading and omit that qualifier from `series.code`, while still modeling
non-default siblings explicitly if they are later curated.

Example shape:

- if the project treats one CPI population basis as the default reading for a
  family, the default series may remain `..._CORE_M_NSA`
- a non-default sibling added later should carry explicit qualifier tokens

Use this sparingly. If omitting the qualifier is likely to confuse a future
reader or block a likely sibling that should also exist, prefer explicit
variant tokens from the start.

## Concept vs indicator vs variant

Use this decision rule:

- New concept: only when the underlying geography-neutral economic idea is
  different.
- New indicator: when the same concept needs a geography-specific grouping.
- New series variant inside an indicator: when the economic idea is the same
  but methodology differs, such as nominal vs real, headline vs core, or
  SA vs NSA.

Examples:

- `GDP` and `real GDP` are one concept (`GDP`) with separate variants in one
  geography indicator.
- Headline CPI and core CPI are one concept (`CPI`) with separate variants in
  one geography indicator.
- Household-basis CPI variants such as one-person and two-or-more-person
  baskets remain one `CPI` concept and one `JP_CPI` indicator; they become
  separate sibling series with different variants.
- A provider redistributor copy of a series is not a new concept and not a new
  canonical series code; it is a new `series_source`.

For compound variant cases, use explicit tokens in the code and a readable
label in the `indicator_variants` row. Example pair:

- `JP_CPI_CORE_1P_HH_M_NSA`
- `JP_CPI_CORE_2PPLUS_HH_M_NSA`

Matching `indicator_variants.label` values might be:

- `Core, one-person household basket`
- `Core, two-or-more-person household basket`

## Ambiguity rule for agents

Agents should make a best-effort inference from source metadata, existing
macrodb rows, and external fact-checking where needed. They do not need to
over-escalate small uncertainties.

But when the uncertainty affects canonical identity, the agent should stop
before creating the `series.code` and raise a proposal instead.

In those cases, the agent should remain in proposal space only. It should not
create a draft canonical `series` row in the main catalog just to reserve or
test a guessed identity.

Examples of identity-level ambiguity:

- whether a provider label refers to the family's default scope or to a
  narrower sibling variant
- whether two labels are true synonyms or distinct methodological variants
- whether a qualifier is peripheral metadata or should become part of the
  canonical variant token set

In those cases, the agent should surface the ambiguity, suggest the most likely
interpretation, and ask for approval rather than silently minting a canonical
series.

## Provider mapping rule

Canonical identity and provider mapping must stay separate:

- canonical identity: `series.code`
- provider mapping: `series_sources.external_code`

This means:

- FRED `GDP` maps to a semantic canonical code such as
  `US_GDP_NOMINAL_Q_SAAR`
- FRED `GDPC1` maps to a semantic canonical code such as
  `US_GDP_REAL_Q_SAAR`
- the FRED ticker never becomes the canonical code just because it is the first
  provider wired up

## Hierarchy governance

Canonical hierarchy edges live in `series_hierarchy_edges` and connect real
`series` rows. They represent additive hierarchy enrichment: a published parent
series can later gain child series without implying the parent identity was
wrong or that parent observations should be recomputed from children.

Default rule: same-concept edges. Parent and child should belong to families
under the same concept unless human review explicitly approves a cross-concept
hierarchy proposal.

Do not create hidden placeholder canonical series solely to mirror provider
indentation. If a provider exposes a useful grouping that is not itself a real
published macro series, keep that structure in research notes or a later
provider-facing metadata surface; do not mint a canonical `series` row for it.

## Weak provider locator governance

Provider locators are reviewable source metadata, not canonical identity. The
schema may allow nullable locator fields for incomplete historical or manual
catalog work, but missing or weak locators should still be surfaced before
onboarding is approved.

Flag weak provider locator metadata when `series_sources.external_code` is
missing, reused across multiple leaf series, only identifies a broad dataset or
table, or depends on an ambiguous provider label. Also flag missing `ref_url` or
a `ref_url` that points only to a broad portal rather than the inspectable
source page used to verify the mapping.

## Naming examples for the first FRED preset

The first curated FRED bootstrap preset uses:

Concepts:

- `GDP`
- `CPI`

Series families:

- `US_GDP`
- `US_CPI`

Raw ingested series (level; no measure suffix):

- `US_GDP_NOMINAL_Q_SAAR`
- `US_GDP_REAL_Q_SAAR`
- `US_CPI_HEADLINE_M_NSA`
- `US_CPI_CORE_M_SA`

The first FRED preset does not register derived series; that is deferred to
a later workflow.

Provider mappings for the first preset:

- `GDP` -> `US_GDP_NOMINAL_Q_SAAR`
- `GDPC1` -> `US_GDP_REAL_Q_SAAR`
- `CPIAUCNS` -> `US_CPI_HEADLINE_M_NSA`
- `CPILFESL` -> `US_CPI_CORE_M_SA`

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
- silently create a broad or underspecified canonical code when the source may
  actually refer to a narrower sibling variant

## Correction discipline for published series

If a published canonical series is later discovered to be underspecified or
mis-scoped, do not let an agent auto-rename it.

Instead, the agent should prepare a dangerous correction proposal describing:

- the suspected problem with the existing canonical identity
- the proposed corrected code and variant scope
- affected source mappings, feeds, observations, and derivations
- whether the repair should be rename-in-place, supersede-and-replace, or leave
  history as-is and route future ingestion to a new series

The default bias after publication should be toward human-reviewed correction,
and often toward supersede-and-replace rather than silent rename.

## Change discipline

When adding new series families or expanding this grammar:

1. Check `CONTEXT.md` first to confirm the concept/family distinction.
2. Follow this document unless there is a strong reason not to.
3. If the naming change would be surprising, hard to reverse, or likely to
   become precedent outside one narrow case, discuss it before implementing.
