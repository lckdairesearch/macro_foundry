# ADR 0026 — Top-level category taxonomy and concept-naming rules

**Status:** Accepted

**Date:** 2026-06-18

Extends [ADR 0025](0025-collapse-concept-indicator-tag-into-category-tree.md)
(which created the `categories` tree). Supersedes the 10-category list in
[ADR 0022 §3](0022-concept-grained-topical-tags.md) (already superseded as a
whole by 0025; this records the replacement taxonomy).

This is **seed/content work inside the accepted ADR 0025 schema** — it does not
change table shape, the strict single-parent tree, or the ≤3-depth convention.

## Terminology

The three tiers of the `categories` tree have standard names, used here and in
CONTEXT.md:

- **Domain** — L1, the top-level root (`kind=topic`). "Root" is a structural
  synonym, used interchangeably below.
- **Subdomain** — L2, a browse grouping (`kind=topic`, or a concept-leaf).
- **Concept** — L3, the attachable `kind=concept` grain a series points at.

## Context

ADR 0025 collapsed `concepts / indicators / tags` into one `categories` tree but
inherited its top-level list unchanged from ADR 0022 §3 (10 economic roots). Two
things made that list insufficient:

- **Scope broadened.** macro_foundry will carry health, education, culture, and
  other social-indicator series, not only the macro/financial spine. The name
  `macrodb` is kept, but the data is no longer macro-only.
- **Some inherited roots were buried or mis-shaped.** Housing was absent;
  population and labour were fused; energy/commodities had been proposed as a
  single bad root that fused a price facet with a quantity facet.

Nine browse taxonomies were surveyed for the redesign (FRED, Eurostat, UK ONS,
Australia ABS, Statistics Canada, Singapore SingStat, Hong Kong C&SD, Taiwan
DGBAS, China NBS). The recurring lesson: agencies disagree most on four contested
nodes — housing, trade, government finance, environment/energy — and the social
surface (health/education/crime/culture) is large but separable.

## Decision

### 1. Fourteen domains plus `OTHER`

A domain earns its place by four tests: (a) it is a **distinct measurement
kind**, not a thematic slice of other domains; (b) the domains are
**collectively exhaustive** enough to keep `OTHER` small; (c) **balanced
population** — no giant domain beside near-empty ones; (d) **stable** — won't
need re-rooting as data grows.

| Domain (`code`) | Scope |
|---|---|
| `PRICES` | Price / inflation indices |
| `NATIONAL_ACCOUNTS` | The SNA framework (GDP and components) |
| `PRODUCTION_BUSINESS_ACTIVITY` | Output, industry, construction, business surveys |
| `RETAIL_CONSUMPTION` | Retail/wholesale trade, consumer demand |
| `LABOR` | Labour market (split out of the old `POPULATION_LABOR`) |
| `MONETARY_BANKING` | Policy-set / banking-system quantities |
| `FINANCIAL_INDICATORS` | Market-determined asset prices |
| `GOVERNMENT_FISCAL` | Government operations: revenue, spending, debt |
| `INTERNATIONAL` | External sector: trade, BoP, FX, reserves |
| `DEMOGRAPHICS` | Population stocks and flows (split out of `POPULATION_LABOR`) |
| `HEALTH` | Health status, risk factors, expenditure, services |
| `EDUCATION` | Enrolment, attainment, expenditure, outcomes |
| `SOCIETY` | Living conditions: income/inequality, crime, welfare, culture, wellbeing |
| `ENVIRONMENT` | Emissions, resources, climate, environmental accounts |
| `OTHER` | Residual / earn-a-root-later holding pen |

### 2. Subdomains (`L2`)

All subdomains are `kind=topic`. Targeting 3–6 per domain.

- **PRICES** — `CONSUMER_PRICES` · `PRODUCER_PRICES` · `TRADE_PRICES` · `PROPERTY_PRICES` · `COMMODITY_PRICE` · `COMPARATIVE_PRICE_LEVELS`
- **NATIONAL_ACCOUNTS** — `GDP_AND_GROWTH` · `EXPENDITURE_COMPONENTS` · `INCOME_AND_SAVING` · `SECTOR_ACCOUNTS` · `INPUT_OUTPUT` · `NATIONAL_WEALTH`
- **PRODUCTION_BUSINESS_ACTIVITY** — `INDUSTRIAL_PRODUCTION` · `SECTORAL_OUTPUT` · `CONSTRUCTION` · `BUSINESS_SURVEYS` · `BUSINESS_DEMOGRAPHY` · `BUSINESS_PROFITS`
- **RETAIL_CONSUMPTION** — `DISTRIBUTIVE_TRADE` · `CONSUMER_CONFIDENCE` · `HOUSEHOLD_SPENDING`
- **LABOR** — `EMPLOYMENT_AND_UNEMPLOYMENT` · `WAGES_AND_EARNINGS` · `PRODUCTIVITY`
- **MONETARY_BANKING** — `MONETARY_AGGREGATES` · `INTEREST_RATES` · `CREDIT_AND_DEBT` · `CENTRAL_BANK_BALANCE_SHEET` · `BANKING_SECTOR` · `FINANCIAL_INCLUSION`
- **FINANCIAL_INDICATORS** — `EQUITY_MARKETS` · `BOND_YIELDS_AND_SPREADS` · `VOLATILITY_AND_RISK` · `FINANCIAL_CONDITIONS`
- **GOVERNMENT_FISCAL** — `REVENUE_AND_TAXATION` · `EXPENDITURE` · `FISCAL_BALANCE` · `PUBLIC_DEBT`
- **INTERNATIONAL** — `MERCHANDISE_TRADE` · `TRADE_IN_SERVICES` · `BALANCE_OF_PAYMENTS` · `EXCHANGE_RATE` · `RESERVES_AND_INVESTMENT_POSITION` · `FOREIGN_INVESTMENT`
- **DEMOGRAPHICS** — `POPULATION_STOCK_AND_STRUCTURE` · `VITAL_STATISTICS` · `MIGRATION` · `HOUSEHOLDS_AND_FAMILIES`
- **HEALTH** — `HEALTH_STATUS_AND_OUTCOMES` · `HEALTH_RISK_FACTORS` · `HEALTH_EXPENDITURE` · `HEALTH_SERVICES`
- **EDUCATION** — `ENROLLMENT_AND_PARTICIPATION` · `ATTAINMENT_AND_LITERACY` · `EDUCATION_EXPENDITURE` · `EDUCATION_OUTCOMES`
- **SOCIETY** — `INCOME_AND_INEQUALITY` · `CRIME_AND_JUSTICE` · `SOCIAL_PROTECTION` · `CULTURE_AND_RECREATION` · `WELLBEING` · `HOUSING_CONDITIONS` · `BASIC_SERVICES_ACCESS`
- **ENVIRONMENT** — `EMISSIONS_AND_AIR_QUALITY` · `NATURAL_RESOURCES` · `CLIMATE`
- **OTHER** — `ENERGY` *(parked)* · `SCIENCE_AND_TECHNOLOGY` · `TOURISM` · `TRANSPORT` · `UNCLASSIFIED`

### 3. Single-parent boundary calls

The strict tree gives each idea exactly one home. The settled placements:

- **Housing has no domain** (it is a theme, not a measurement kind). It splits four
  ways: price/rent → `PRICES/PROPERTY_PRICES`; construction →
  `PRODUCTION_BUSINESS_ACTIVITY/CONSTRUCTION`; mortgage credit →
  `MONETARY_BANKING/CREDIT_AND_DEBT`; tenure/overcrowding →
  `SOCIETY/HOUSING_CONDITIONS`. A future `series_collections` view (ADR 0025 §6)
  reassembles a cross-cutting "housing" browse.
- **Exchange rates** → `INTERNATIONAL` (following ADR 0022's external-sector call,
  not `FINANCIAL_INDICATORS`).
- **Commodities** split by measurement kind: *price* → `PRICES/COMMODITY_PRICE`;
  *physical output/consumption* → `PRODUCTION_BUSINESS_ACTIVITY/SECTORAL_OUTPUT`
  (or `OTHER/ENERGY` for energy carriers). "Oil price" and "oil consumption" are
  different series in different roots, by design.
- **Private debt-to-GDP** → `MONETARY_BANKING/CREDIT_AND_DEBT` (a credit stock;
  the `/GDP` is normalization, not a national-accounts reclassification). This
  L2 is named `CREDIT_AND_DEBT` rather than `BANK_CREDIT` to cover bond financing.
- **Income** splits: wages → `LABOR`; household spending → `RETAIL_CONSUMPTION`;
  distribution/inequality → `SOCIETY`.

### 4. The parking rule for `OTHER`

`OTHER` holds in-scope-but-uncertain themes until real series justify a domain:
`ENERGY`, `SCIENCE_AND_TECHNOLOGY`, `TOURISM`, `TRANSPORT`. A growing population
in any of these is the signal to promote it to a domain (the inverse of ADR
0022's "large `OTHER` = missing category" test).

### 5. Concept-naming rules (the `kind=concept` grain)

`L3` is not forced. "Depth" here means *where the attachable `concept` node sits*,
which is ragged:

- **An `L2` may itself be the concept** (`kind=concept`, no children) when the
  subdomain maps to one economic idea — e.g. `POLICY_RATES`, `FISCAL_BALANCE`.
- **An `L2` fans to `L3` concepts** only when there are ≥2 genuinely distinct,
  cross-country ideas series must be told apart by — e.g. `CONSUMER_PRICES` →
  `CPI_ALL_ITEMS`, `CPI_CORE`.

Three rules govern concept identity:

1. **Concepts name the economic *function*, not a country's statistical *label*.**
   `BROAD_MONEY` / `NARROW_MONEY` / `MONETARY_BASE`, never `M2`/`M3`/`M4` (these
   are not comparable across countries). A country's native label and exact
   composition live on the **series** (`alt_name`, methodology, provider
   `external_code`). Same rule for `UNEMPLOYMENT_RATE` (ILO idea),
   `GENERAL_GOVERNMENT_DEBT` (not Maastricht/gross/net), `POLICY_RATE`.
2. **Concept is the generalizable idea; variants are series-level, by flag.** A
   common methodological distinction (e.g. core-CPI flavour: ex-food-energy vs
   ex-fresh-food vs trimmed-mean) does **not** mint a concept per variant — it is
   a structured **flag** on the series when common enough for machine filtering,
   prose (`alt_name`/`description`) when rare. This is the existing CONTEXT.md
   rule (structured field when the distinction needs consistent cross-series
   filtering). `CPI_CORE` is one generalizable concept; its exclusion list is a
   series flag.
3. **Cross-country equivalence is a separate, later layer — not the tree's job.**
   "Is US M2 ≈ UK M4?" is handled downstream (a crosswalk/mapping or the existing
   embeddings), not by the category tree. The tree only places both under the
   same generalizable concept; it asserts comparability of *idea*, not identity
   of *method*. Harmonized ≠ identical is accepted and not forced here.

Seed the **topic skeleton** (roots + `L2`) plus the handful of **universal
concepts** every country has (`CPI_ALL_ITEMS`, `GDP`, `UNEMPLOYMENT_RATE`,
`POLICY_RATE`, …) now; let the long tail of concepts **accrete via
bootstrap/onboarding** as series arrive (consistent with ADR 0025's stance that
concepts are generated, not seeded en masse). No placeholder concepts, no
mirroring provider table layouts (ADR 0010 no-placeholder rule still binds).

## Validation (2026-06-18)

A multi-agent coverage test (workflow `wz3k53mcb`) sampled **388 real published
series across 12 sources** — the nine surveyed NSOs plus IMF, World Bank WDI, and
OECD — and classified each against the cleaned tree. **94% (365/388) mapped
cleanly**; every source scored ≥ 88%. Roughly one third of all hits were
*series-variant* placements (M2→`BROAD_MONEY`, 10Y yield→`GOVERNMENT_BOND_YIELD`,
CPI-ex-food→`CPI_CORE`), confirming the rule-5 design: a general concept with the
specifics on the series is what carries coverage from ~60% to 94%. The taxonomy
is therefore neither too specific (variants absorb cleanly) nor — with one
exception below — too general.

### Additions adopted from the validation

Distinct, cross-country concepts the sample surfaced that had no home (so were
added, not left to accrete):

- New L2 subdomains: `PRICES > COMPARATIVE_PRICE_LEVELS` (PPP price levels — spatial,
  distinct from temporal CPI); `PRODUCTION_BUSINESS_ACTIVITY > BUSINESS_PROFITS`
  (the only gap recurring across two sources — ABS, China NBS — fitting no
  existing node); `MONETARY_BANKING > FINANCIAL_INCLUSION` (the IMF FAS dataset);
  `DEMOGRAPHICS > POPULATION_BY_GROUP` (ethnicity/language/identity census theme);
  `SOCIETY > BASIC_SERVICES_ACCESS` (WDI water/sanitation/electricity access).
- New concepts under existing subdomains: bank soundness family (IMF FSI:
  `BANK_CAPITAL_ADEQUACY_RATIO`, `BANK_RETURN_ON_ASSETS`, `BANK_RETURN_ON_EQUITY`,
  `BANK_LIQUIDITY_RATIO`) under `BANKING_SECTOR`; `UNDERNOURISHMENT_RATE` under
  `HEALTH_RISK_FACTORS`; `URBANIZATION_RATE` under `POPULATION_STOCK_AND_STRUCTURE`;
  `DWELLING_STOCK` under `HOUSING_CONDITIONS`; `NEW_ORDERS` / `EXPORT_ORDERS`
  (forward demand, nowcasting) under `BUSINESS_SURVEYS`.

### Routing rule (the one "too general" fix)

`GDP_REAL` was a classifier magnet for sectoral and regional value-added. No
structural change; instead a routing convention: **value-added by industry →
`SECTORAL_OUTPUT`; regional aggregates → `GDP_*` with a region series dimension.**
`GDP_REAL` is not a catch-all.

### Deliberately held

- `MONEY_VELOCITY` (a derived ratio — attach to `MONETARY_AGGREGATES` later) and
  `PAYMENT_SYSTEM_ACTIVITY` (genuinely niche) — left to accrete via onboarding.
- Zero-hit leaves (`WELLBEING`, `CLIMATE`, `CULTURE_AND_RECREATION`,
  `SOVEREIGN_CDS_SPREAD`, `DIVIDEND_YIELD`, `FLOW_OF_FUNDS`, `EDUCATION_OUTCOMES`)
  are **kept, not pruned**: the sample is statistical-office/IO-heavy and
  under-represents market-data and met-office series, which is where these
  populate. Empty leaves cost nothing.

### Grain discipline: dimensions that are series flags, not concepts

A follow-up consistency sweep over all L3 concepts found the tree was over-grained
along predictable axes — the same `M2`→`BROAD_MONEY` over-specificity, repeated.
The standing rule (extends §5.2): **the following dimensions are always
series-level flags, never separate concepts.**

- **Sector / industry** — `SECTORAL_OUTPUT` (was agri/mining/services), sector
  PMIs → `PMI`, manufacturing IP → `INDUSTRIAL_PRODUCTION_INDEX`.
- **Direction (in/out)** — exports/imports → `MERCHANDISE_TRADE_FLOW` /
  `SERVICES_TRADE_FLOW`; immigration/emigration → `MIGRATION_FLOW`;
  FDI in/out → `FDI_FLOW`; import/export price → `TRADE_PRICE_INDEX`. The
  `*_BALANCE` / `NET_*` derived figure stays its own concept.
- **Basis (nominal/real, value/volume)** — `RETAIL_SALES` (was value/volume).
  *(GDP nominal/real is the one documented exception, kept by convention.)*
- **Normalization (per-capita, per-student, per-area, /GDP)** — folded into `GDP`,
  `HEALTH_EXPENDITURE`, `EDUCATION_EXPENDITURE`, `PHYSICIAN`, `FINANCIAL_ACCESS_POINT`,
  and `ENERGY_CONSUMPTION` (energy intensity).
- **Substance / commodity / pollutant** — `COMMODITY_PRICE` (oil/gas/gold);
  CO₂ → `GHG_EMISSIONS` (gas flag); PM2.5 → `AIR_QUALITY` (pollutant flag). The
  emissions-flow vs ambient-concentration split IS kept (distinct measurement
  kinds).
- **Component / breakdown** — CPI components → `CPI_ALL_ITEMS`; youth →
  `UNEMPLOYMENT_RATE`; homicide → `CRIME_RATE`; cause/age mortality →
  `MORTALITY_RATE`; pensions → `SOCIAL_SPENDING`; borrower-sector debt →
  `CREDIT_TO_PRIVATE_SECTOR`; age AND social-group structure → `TOTAL_POPULATION`;
  education level → `ENROLLMENT_AND_PARTICIPATION`; basic-service type →
  `BASIC_SERVICES_ACCESS`; retail product (autos) → `RETAIL_SALES`;
  exchange-rate basis/scope → `EXCHANGE_RATE`; ATM/branch → `FINANCIAL_ACCESS_POINT`.

**Kept as distinct concepts** (genuinely different measurement kinds or watched
headlines, the `CPI_CORE` bar): `CPI_CORE`, `TAX_REVENUE`, `INTEREST_PAYMENT`,
`REMITTANCES`, the money tiers, the SNA expenditure components, vital statistics,
PPI input/output, govt vs corporate bond yield, `HOUSEHOLD_NET_WORTH` (a
recorded watched-headline exception). Several collapsed L2s with a single
resulting concept are **concept-leaf** L2s (`SECTORAL_OUTPUT`, `COMMODITY_PRICE`,
`EXCHANGE_RATE`, `BASIC_SERVICES_ACCESS`, `HEALTH_EXPENDITURE`,
`EDUCATION_EXPENDITURE`, `ENROLLMENT_AND_PARTICIPATION`, `HOUSEHOLD_SPENDING`,
`WHOLESALE_TRADE` now an L3 under `DISTRIBUTIVE_TRADE`). A follow-up pass folded
single-concept leaves that had a natural sibling home: `POPULATION_BY_GROUP` →
group flag on `TOTAL_POPULATION` (matching `POPULATION_BY_AGE`); `WHOLESALE_TRADE`
→ under `DISTRIBUTIVE_TRADE` (retail+wholesale); and `POLICY_RATE` → into a new
`INTEREST_RATES` L2 (with `INTERBANK_RATE`/`LENDING_RATE`/`DEPOSIT_RATE` moved out
of `BANKING_SECTOR`, which keeps balance-sheet & soundness).

### Naming conventions settled

- **Concept codes are singular; display `name` keeps the idiomatic plural.** The
  `code` is a key (`BANK_DEPOSIT`, `HOUSING_START`), the `name` is prose
  ("Bank Deposits", "Housing Starts"). Topic/subdomain codes may stay plural — they
  name categories, not measures.
- **Abbreviation allow-list** (sanctioned; everything else spelled out):
  `CPI, PPI, GDP, GNI, FDI, PMI, CDS, CO2, GHG, PM25`. This records the kept
  exceptions so the rule (no abbreviations by default) doesn't drift as concepts
  accrete.
- **`SAVING_RATE` → `NATIONAL_SAVING` / `HOUSEHOLD_SAVING`** — a concept is
  presentation-agnostic; rate-vs-level is a series flag. `_RATE` is kept in a code
  only where the rate is the sole canonical form with no separately-tracked level
  (`UNEMPLOYMENT_RATE`, `BIRTH_RATE`, `URBANIZATION_RATE`).
- **Plural-idiom exceptions** (singular rule does not apply — protected
  basket/measure idioms): `CPI_ALL_ITEMS`, `PPI_ALL_ITEMS`, `MEAN_YEARS_SCHOOLING`.

### Open-item dispositions

Two homeless concepts were **added**: `INVENTORIES` (business inventory stock,
distinct from the `CHANGE_IN_INVENTORIES` flow) under `INDUSTRIAL_PRODUCTION`, and
`FDI_STOCK` (position) under `FOREIGN_INVESTMENT`. `MARRIAGE_RATE`/`DIVORCE_RATE`
kept in `HOUSEHOLDS_AND_FAMILIES` and `INPUT_OUTPUT` kept as a concept-leaf (both
decided). The R&D-vs-ICT split inside `SCIENCE_AND_TECHNOLOGY` is deferred until
that subdomain is promoted out of `OTHER` (accrete-later).

### Final review (workflow `wwfxszcgz`)

A five-lens adversarial review + judge over the finalized tree returned
**`fix_then_ship`**: structurally sound (single-parent, depth ≤3, no duplicate
codes, all boundary calls intact), with only code-level survivors — three of
which the dedup pass had already purged elsewhere. Applied: singularized the
concept-leaf codes that slipped (`POLICY_RATE`, `EXCHANGE_RATE`, `COMMODITY_PRICE`,
`PHYSICIAN`, `HOSPITAL_BED`); spelled out `RESEARCH_AND_DEVELOPMENT_EXPENDITURE`;
demoted three normalization/component concepts (`ENERGY_INTENSITY`,
`RENEWABLE_ENERGY_SHARE`, `ENVIRONMENTAL_TAX_REVENUE`) to series flags, which
emptied and so **dropped** the `ENVIRONMENTAL_ACCOUNTS` L2; folded
`ATM_DENSITY`/`BANK_BRANCH_DENSITY` into `FINANCIAL_ACCESS_POINT`; and moved
`OPERATING_SURPLUS` to `NATIONAL_ACCOUNTS/INCOME_AND_SAVING` (income-approach GDP
component), leaving `BUSINESS_PROFITS` holding the firm-level `CORPORATE_PROFIT`.
The judge rejected every reviewer proposal that re-litigated a settled decision
(re-splitting collapsed concepts, a new `INTEREST_RATES` L2, downgrading
`INPUT_OUTPUT`).

After all passes (including the concept-leaf follow-ups: `JOB_VACANCIES`/
`HOURS_WORKED` nested under `EMPLOYMENT_AND_UNEMPLOYMENT`; `POPULATION_BY_GROUP`
→ group flag; `WHOLESALE_TRADE` → under `DISTRIBUTIVE_TRADE`; `INTEREST_RATES`
subdomain; `MOTOR_VEHICLE_SALES` → product-category flag on `RETAIL_SALES`), the tree
stands at **15 domains · 71 subdomains · 157 concepts = 243 nodes** (down from 207
concepts). The full result, per-source breakdown, and export-ready grid live in
`docs/schema/category_taxonomy.xlsx`.

## Consequences

- The `seed/data/` category seed grows from a flat tag list to a ~14-domain,
  ~70-subdomain topic skeleton plus universal concepts. This is the seed `seed/data/`
  currently lacks.
- When the V8 schema slice lands (ADR 0025), CONTEXT.md's glossary gains the
  concept-naming rules above and drops the V7 concept/indicator/tag language.
- No schema, migration, or model change is implied by *this* ADR — it is content.
- `OTHER` is now a managed promotion queue, not a junk drawer; its growth is a
  monitored signal.

## Alternatives considered

- **Keep the inherited 10 roots, add depth only.** Rejected once social
  indicators entered scope: health/education/culture would pile into `OTHER`,
  tripping the missing-category signal.
- **`HOUSING_REAL_ESTATE` as a domain.** Rejected: it is a theme that
  cannibalizes four measurement-kind domains and fails the distinct-measurement
  test (it generated four single-parent puzzles). Served instead by a future
  collection.
- **`ENERGY_COMMODITIES` as one domain.** Rejected: fuses a price facet with a
  quantity facet — two half-domains. Energy parked in `OTHER`; commodity prices
  and quantities routed by measurement kind.
- **Grouped Eurostat-style super-domains** (e.g. "Economy & Finance", "Social").
  Rejected: a layer above the domains pushes concept leaves to `L4`, breaking the
  ≤3 depth convention. A flat ~14-domain list stays inside the cap.
- **`M2`/`M3`/`M4` (and other national labels) as concepts.** Rejected: not
  country-neutral; the harmonized function is the concept, the label is series
  metadata.
- **A concept per methodological variant.** Rejected: concept explosion; variants
  belong on the series as flags or prose.
