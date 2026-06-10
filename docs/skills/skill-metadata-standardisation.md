---
status: draft
---
# skill-metadata-standardisation

**Status:** draft

The body is content-complete; the skill is held at `draft` until the
operator reviews and signs off on the seed exemplars in the body. Promote
to `accepted` after that review.

## Scope

How the proposal drafter writes prose fields (`series.description`,
`series.name`, `series_family.description`, `concept.description`, and
`series_family_members.variant`) so the catalog has consistent, readable,
non-redundant language across related series, and the discipline for when
to propose updates to existing prose versus letting it grandfather in.

This skill governs prose only. It does not cover canonical code grammar
(see [skill-canonical-code-grammar](skill-canonical-code-grammar.md)),
concept/family/variant boundaries (see
[skill-concept-vs-family-vs-variant](skill-concept-vs-family-vs-variant.md)),
or structural fields (units, frequency, seasonal adjustment, etc.). Those
are governed elsewhere.

The architectural rationale for this skill, the cohort retrieval node,
the `suggest_human_apply` action, and the four-trigger harmonisation
structure lives in
[ADR 0013](../adr/0013-metadata-standardisation.md).

## When triggered

- node is `draft_proposal`, `governance_review`, or
  `data_correctness_review`
- the proposal under construction touches a prose field (`description`,
  `name`, `variant`) on any of `concept`, `series_family`, `series`,
  `series_family_members`
- OR the harmonisation side-output of `draft_proposal` is non-empty (the
  drafter has proposed updates to existing prose)

The `Seed exemplars` sub-section is conditionally loaded only when
`reference_metadata.cohort_A_empty == true` (no `series_family` siblings
exist yet for the family under draft). When siblings exist, the cohort
is the anchor and exemplars are unnecessary noise.

## Body

### Part 1 — Drafting new prose (forward direction, primary purpose)

The proposal drafter never writes prose blind. Before drafting any prose
field, it reads `reference_metadata`, populated by the upstream
`gather_reference_metadata` node. That state field carries three
cohorts:

- **Cohort A** — sibling series in the same `series_family`. Strongest
  anchor; new prose must read as coherent with siblings.
- **Cohort B** — series for the same `concept` across geographies.
  Provides house voice for how this concept is described system-wide.
- **Cohort C** — series for the same `provider` and `concept`, joined
  through `series_sources`. Captures provider-specific terminology and
  conventions worth preserving.

The starting assumption is that what is already written is correct. The
burden is on the drafter to justify any deviation.

#### Hard rules for new prose

1. **`series.name` follows a geography-prefixed pattern.** Start with the
   `geographies.code` (handles ISO3 countries, blocs, regions, and
   subnational units uniformly), then an em-dash, then the human-readable
   description. Example:
   `USA – Consumer Price Index for All Urban Consumers: All Items Less Food and Energy in U.S. City Average`
2. **Structural differences must surface in prose.** When this series
   differs from siblings on a controlled-vocabulary structural field
   (`seasonal_adjustment`, `frequency`, `measure`, `basket`,
   `household_scope`, etc.), the difference must appear in both `name`
   and `description`. Never let SA vs NSA hide in the row's structural
   fields alone.
3. **Descriptions do not contain internal codes.** `series.code`,
   `concept.code`, `series_family.code` are identity, not prose.
   Descriptions describe the series in human terms; codes belong
   elsewhere.
4. **No request-encoding or runtime-implementation detail.** Descriptions
   must not mention selector configuration, endpoint URLs, request
   parameters, file path patterns, or anything that belongs in the
   `ingestion_feed` configuration.
5. **No temporal hedging.** Avoid phrases like "as of 2024",
   "currently", "most recent" — prose should remain valid as data
   evolves.
6. **Present tense, prefer active voice, no first person.**
7. **`description` soft cap 2000 characters.** Minor exceedance is OK
   when content is genuinely necessary; bloated descriptions are a
   `Request changes` flag at Gate 1.
8. **`variant` is one short noun phrase, ≤120 characters.** The
   structural distinctions are encoded on the `series` row itself;
   `variant` is the human label only.

#### Soft conventions (emerge from cohorts)

- The voice, rhythm, and qualifier ordering of how methodology is
  described should match cohort A first, then cohort B. Do not reinvent
  phrasing siblings have already settled on.
- Source provenance ("Published by the U.S. Bureau of Labor Statistics")
  should appear in `description` for a flagship-style series in a family.
  Sibling variants inherit the family's source context and should not
  repeat it unless the variant is genuinely from a different publisher.
- Acronyms should be expanded on first use within a single description.
- Qualifier phrasing (e.g., "Less Food and Energy" vs "Excluding Food
  and Energy" vs "Ex Food & Energy") should converge with what cohort A
  and cohort B already use. When introducing a new qualifier for a new
  family, prefer the most explicit and least abbreviated form.

#### When a cohort is empty

If cohort A is empty (this is the first series in its family), the
`Seed exemplars` sub-section below is loaded. Use the exemplars as the
voice anchor.

If cohort B is also empty (this is the first series for its concept
system-wide), write the prose carefully — every future series in this
concept will anchor on what is written here. The state flag
`is_first_in_family` triggers extra governance scrutiny in the reviewer
node.

If cohort C is empty (this is the first series from this provider for
this concept), the prose anchors on A and B and adopts no provider-
specific phrasing it does not already inherit from elsewhere.

### Part 2 — Proposing updates to existing prose (reactive direction)

The default is **do not touch existing prose.** Existing prose is
grandfathered. Propose an update to an existing prose field only when one
of the four triggers below fires.

#### The closed list of triggers

| Trigger | Bar | What it means |
|---|---|---|
| `factual_incompleteness` | Low — always propose | Existing prose omits a structural difference the row's own schema fields record. A reader of the prose alone would be misled. Example: description says "Japan CPI" but `seasonal_adjustment = NSA` and the prose nowhere indicates that. |
| `factual_error` | Low — always propose | Existing prose contradicts the row's structural fields or the published source. Example: description says "monthly" but `frequency = quarterly`. |
| `family_outlier` | High — needs a chorus | Within `series_family`, this row's prose structure diverges significantly from siblings' shared pattern. Requires showing a clear consensus among siblings. A single sibling disagreeing is not consensus. |
| `house_voice_outlier` | Highest — needs a louder chorus | Cross-cohort B, this row's terminology, framing, or structure no longer matches the cohort B consensus. Requires showing clear consensus across multiple cohort B entries. Cosmetic differences excluded. |

#### Anti-patterns (never proposable as updates, regardless of trigger)

- Synonym swaps: `ex` ↔ `excluding`, `&` ↔ `and`, `pct` ↔ `percent`
- Capitalisation or punctuation normalisation
- Reordering qualifiers when both orderings are grammatical
- Tense or voice swaps when both forms are correct
- Aesthetic preferences ("reads better", "more concise")
- Single-sibling disagreement (no clear consensus to anchor on)
- Retroactively applying the hard rules in Part 1 to grandfathered prose
  (length cap, geography prefix format, temporal hedging, etc.)

The anti-pattern list exists because each item is a known way that
"style drift" pretends to be a meaningful trigger when it is not.

#### Per-item evidence structure

Every harmonisation side-output item must include:

- `series_id`
- `field`: `description` | `name` | `variant`
- `trigger_code`: one of the four above
- `evidence`:
  - for factual triggers: cite the conflicting `schema_field` or
    `source_url`
  - for outlier triggers: list `cohort_members` (the series_ids whose
    consensus is being invoked), `shared_pattern` (one line describing
    the consensus structural pattern), `this_row_divergence` (one line
    describing what makes this row different)
- `justification`: one line, ≤200 characters, references the evidence
- `proposed_diff`: `{ before, after }`

Items with missing or empty evidence are dropped before reaching Gate 1.

#### Governance reviewer scope for harmonisation items

The governance reviewer evaluates each harmonisation item against its
claimed trigger:

- Factual triggers: verify the cited schema field or source URL is real
  and supports the claim.
- Outlier triggers: verify the cohort members really share the claimed
  pattern, that this row really diverges structurally, that the
  divergence is not on the anti-pattern list, and that the chorus is
  loud enough to warrant the proposal.

Weak harmonisation items become reviewer flags, not silent drops, so the
operator sees what the drafter wanted and why the reviewer pushed back.

#### Advisory budget

A typical onboarding session produces:

- 0–2 factual harmonisation items (factual problems are rare)
- 0–1 style outlier item (style outliers are very rare)

Sessions proposing more than ~3 total harmonisation items should make
the reviewer suspicious that the drafter is over-eager. This is
advisory, not a hard cap.

### Part 3 — Mutation matrix

Different prose-adjacent fields are touched differently by the agent:

| Field | Agent can mutate after Gate 1 approval | Agent can only propose; human applies via SQLAdmin |
|---|---|---|
| `series.name` | ✅ | — |
| `series.description` | ✅ | — |
| `series_family.description` | ✅ | — |
| `concept.description` | ✅ | — |
| `series_family_members.variant` | ✅ | — |
| `concept.name` | — | ✅ |
| `series_family.name` | — | ✅ |
| `series.code`, `concept.code`, `series_family.code` | — | ✅ (and only via Gate 2 if changing an existing code) |
| Structural enum-backed fields (`unit_code`, `frequency`, `seasonal_adjustment`, etc.) | — | ✅ (may require enum-gap escalation, deferred to a separate ADR) |

For propose-only fields, the agent emits a `change_proposal_item` with
`action = suggest_human_apply`. The executor's `apply_catalog` node
**skips** those items; they live in `change_proposals` with
`validation_status = pending_human_apply` until the operator marks them
applied in SQLAdmin (flipping the status to `applied_by_operator` and
stamping `applied_at` plus `applied_by`).

### Seed exemplars

Loaded only when `reference_metadata.cohort_A_empty == true`. Status:
**proposed; awaiting operator sign-off** before promoting the parent
skill from `draft` to `accepted`.

#### Exemplar 1 — Headline level series, monthly index, NSA

- **`concept.code`:** `CPI`
- **`concept.name`:** Consumer Price Index
- **`concept.description`:** A measure of the average change over time
  in the prices paid by consumers for a representative basket of goods
  and services. Used as the primary indicator of consumer price
  inflation.
- **`series_family.code`:** `US_CPI`
- **`series_family.name`:** U.S. Consumer Price Index for All Urban
  Consumers
- **`series_family.description`:** The CPI for All Urban Consumers
  (CPI-U) is the U.S. Bureau of Labor Statistics' headline measure of
  consumer price inflation in the United States. It tracks the average
  change over time in prices paid by urban consumers for a
  representative basket of goods and services. Member series differ in
  basket scope (all items, core, components), transformation (level,
  year-over-year change), and seasonal adjustment.
- **`series.name`:** USA – Consumer Price Index for All Urban Consumers:
  All Items in U.S. City Average
- **`series.description`:** Monthly index level of the Consumer Price
  Index for All Urban Consumers (CPI-U) covering all items, U.S. city
  average. Published by the U.S. Bureau of Labor Statistics. Not
  seasonally adjusted. Reference base period 1982-84 = 100.
- **`variant`:** All Items, NSA, monthly index

#### Exemplar 2 — Same family, transformed (12-month % change)

- **`series.name`:** USA – Consumer Price Index for All Urban Consumers:
  All Items, 12-Month Percent Change in U.S. City Average
- **`series.description`:** Twelve-month percentage change in the
  Consumer Price Index for All Urban Consumers (CPI-U) covering all
  items, U.S. city average. Not seasonally adjusted. Derived from the
  CPI-U all-items index level.
- **`variant`:** All Items, NSA, 12-month percent change

The description does not repeat "Published by the U.S. Bureau of Labor
Statistics"; the family-level description already carries the publisher
context, and sibling variants inherit it.

#### Exemplar 3 — Same family, scope-narrowed (core), seasonally adjusted

- **`series.name`:** USA – Consumer Price Index for All Urban Consumers:
  All Items Less Food and Energy in U.S. City Average
- **`series.description`:** Monthly index level of the Consumer Price
  Index for All Urban Consumers (CPI-U) covering all items excluding
  food and energy ("core CPI"), U.S. city average. Seasonally adjusted.
  Reference base period 1982-84 = 100. Core CPI tracks underlying
  inflation by removing the most volatile components of the headline
  basket.
- **`variant`:** Core (ex food and energy), SA, monthly index

Both the seasonal-adjustment difference ("Seasonally adjusted") and the
scope-narrowing difference ("All Items Less Food and Energy") appear
explicitly in `name` and `description`. The structural fields on the
row record them too; the prose makes them legible to a human reader.

#### Exemplar 4 — Different concept (GDP), to show the pattern generalises

- **`concept.code`:** `GDP`
- **`concept.name`:** Gross Domestic Product
- **`concept.description`:** The total monetary value of all final goods
  and services produced within a country's borders during a specified
  period.
- **`series_family.code`:** `US_GDP`
- **`series_family.name`:** U.S. Gross Domestic Product
- **`series.name`:** USA – Real Gross Domestic Product, Seasonally
  Adjusted Annual Rate, Billions of Chained 2017 Dollars
- **`series.description`:** Quarterly level of real gross domestic
  product (GDP) for the United States, expressed at a seasonally
  adjusted annual rate in billions of chained 2017 dollars. Published by
  the U.S. Bureau of Economic Analysis as part of the National Income
  and Product Accounts. Real GDP measures the total value of goods and
  services produced in the United States after adjusting for changes in
  prices.
- **`variant`:** Real, SAAR, chained 2017 dollars

#### Exemplar 5 — Non-USA geography, to show the prefix pattern

- **`series_family.code`:** `GBR_CPIH`
- **`series_family.name`:** U.K. Consumer Prices Index Including Owner
  Occupiers' Housing Costs
- **`series.name`:** GBR – Consumer Prices Index Including Owner
  Occupiers' Housing Costs: All Items, Index 2015 = 100
- **`series.description`:** Monthly index of the Consumer Prices Index
  including Owner Occupiers' Housing Costs (CPIH) for the United Kingdom
  covering all items. Published by the Office for National Statistics.
  Not seasonally adjusted. Reference base period 2015 = 100. CPIH
  extends the standard CPI by including owner-occupied housing costs and
  is the ONS's preferred headline measure of consumer price inflation.
- **`variant`:** All Items (CPIH), NSA, monthly index

The `GBR` prefix comes from `geographies.code`, not "United Kingdom" or
"UK". The prefix is always the geography code; the long name is fine
inside the description body.

## Notes for the reader of this skill

- This skill is the answer to "how do I write prose that ages well in a
  catalog that grows over time, without prose drifting cosmetically
  every time a new series arrives". The bias is toward inaction on
  existing prose and consistency in new prose.
- The four-trigger asymmetry (factual cheap, style expensive) exists
  because cosmetic edit churn is a real failure mode of agent-assisted
  catalog work and was an explicit design constraint set by the
  operator.
- ADR 0013 records the architectural rationale and the associated
  state-machine changes (`gather_reference_metadata` and
  `classify_extraction_mode` as new nodes, `suggest_human_apply` as a
  new proposal-item action, scenario 2 routing through Gate 1 companion
  items rather than Gate 2).
