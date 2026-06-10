# Glossary

Macrodb has unusual domain terminology. Agents that conflate these terms produce
wrong code, wrong tests, and wrong SQL. Read this file before any work touching
the data model.

When you find yourself defining a new domain term, add it here.

## Core conceptual layer

### Concept

A geography-neutral economic idea. Examples: `CPI`, `GDP`, `UNEMPLOYMENT_RATE`,
`CURRENT_ACCOUNT_BALANCE`, `HOUSEHOLD_CONSUMPTION`.

A concept has a `code` (canonical identifier) and a `name`. It does **not** have
a geography — the same concept manifests differently in different countries.

Concepts are curated. They live in the `concepts` table and are typically added
via the API or admin (not seeded en masse).

### Geography

A country, subnational region, region, bloc, or "world." Identified by an ISO
code where possible:

- **Country** — ISO 3166-1 alpha-3 (`USA`, `GBR`, `JPN`).
- **Subnational** — administrative subdivision within a country, typically ISO
  3166-2 (`US-CA`, `US-NY`). Has a `parent_geography_id` pointing to the
  country.
- **Subnational region** — a country-scoped grouping geography such as Japan's
  `chiho` (`Kanto`, `Tohoku`) or US groupings like `Midwest`. Usually uses an
  internal code. Has a `parent_geography_id` pointing to the country. Its
  member prefectures, states, or provinces are linked through
  `geography_memberships`, not through a forced child tree.
- **Region** — World Bank or internal cross-country designation (`EAS` for East
  Asia, `MEA` for Middle East and North Africa).
- **Bloc** — internal slug (`G7`, `OECD`, `BRICS`, `EMU`). Bloc membership is
  tracked separately in `geography_memberships`, with optional `start_date` /
  `end_date` for membership changes over time.
- **World** — `WLD`.

`parent_geography_id` is the **country anchor** for `subnational` and
`subnational_region`. For `subnational`, that anchor is also the strict
administrative parent. For `subnational_region`, it means "belongs to this
country" rather than "is the only grouping tree for this country."
`parent_geography_id` is **never** used for bloc membership, and it is not used
to force one subnational-region hierarchy; those memberships live in
`geography_memberships`.

### Series family

A group of related series within a single geography for a single concept.
Examples: `US_CPI`, `JP_CPI`, `JP_HOUSEHOLD_CONSUMPTION`.

A family connects a concept (geography-neutral) to a geography. Within a family,
multiple series may exist — different variants of the same underlying measurement.

Examples within `US_CPI`:
- US CPI All Items, NSA, monthly index, level
- US CPI All Items, SA, monthly index, level
- US CPI Core (ex food and energy), SA, monthly index, level
- US CPI All Items, YoY % change, monthly

Each is a separate `series` row attached to the `US_CPI` family.

A series can belong to at most one family (enforced by `UNIQUE(series_id)` on
`series_family_members`). If a series feels like it belongs to multiple families,
it probably needs to be a variant of one or a derived series in another, not
double-assigned.

### Series

A specific economic time series with a single set of methodological attributes:
geography, frequency, unit, measure, seasonal adjustment, vintage policy, and
so on.

`code` is the canonical identifier (internal — not necessarily the provider's
code; see `series_sources` for provider mappings). `code` is globally UNIQUE.

A series has `origin_type` of `ingested`, `derived`, or `both`:
- **Ingested** — observations come from one or more external providers via
  `series_sources`, request-level `ingestion_feeds`, and
  `ingestion_feed_members`.
- **Derived** — observations are computed from other series per `derived_series`
  and `derivation_inputs`.
- **Both** — rare; covers cases where ingestion is the primary source but
  derivations fill backfill periods or vice versa.

### Published series / publication boundary

A canonical series crosses the publication boundary once it is no longer just a
draft catalog idea and has become part of the operational database surface.

In practice, a series should be treated as published once it has meaningful
downstream linkage such as a provider/source mapping, ingestion configuration,
stored observations, or derived-series lineage.

Before the publication boundary, identity corrections are relatively cheap.
After the publication boundary, changes to canonical identity are dangerous
because other database records and future reasoning may already depend on that
series as defined.

### Variant

A field on `series_family_members.variant`. Human-readable description of how
this series differs from its siblings in the family. Examples: "Core ex fresh
food", "Two-or-more-person households", "Headline NSA".

This is intentionally free text. The structural distinctions (measure, unit,
seasonal_adjustment, etc.) are encoded on the series itself; `variant` is the
human label for the combination.

### Default variant

A family's default variant is the methodological scope that macrodb treats as
the baseline reading for that family when no extra qualifier is included in the
canonical `series.code`.

Not every provider-exposed distinction needs to become part of canonical
identity. A default variant exists only when the omission is an intentional
curation choice, not when the scope is still ambiguous.

`variant` is robust enough for human-facing cataloging and rare methodological
edge cases inside a family. It is not a normalized taxonomy column. If a
distinction becomes common enough that the system needs consistent cross-series
machine filtering on it, that should become a separate structured field or
model rather than more convention piled into free text.

### Series hierarchy

A canonical parent-child structure between `series` rows used when macrodb
needs to represent a decomposition tree rather than only flat sibling variants.

This hierarchy is part of the canonical series layer, not just a provider-side
ingestion aid. It may therefore outlive any one provider payload shape and may
be shared across providers that publish the same underlying decomposition.

Series hierarchies may be ragged. A branch does not need every intermediate
depth to be populated just because another branch has it.

When a decomposition needs an intermediate grouping node, that grouping should
exist as an explicit canonical `series` row only when it is analytically
meaningful or directly published by a source. Macrodb should not create hidden
canonical placeholder nodes solely to satisfy a provider's visual indentation or
missing intermediate display levels.

Series hierarchy enrichment may be additive over time. A published parent series
may later gain newly curated child series without that parent's canonical
identity being treated as wrong.

If a parent series has its own published observations, macrodb should continue
to store the parent's observed values even when child series exist and even when
an aggregation rule is known. The hierarchy does not imply that the parent is
merely a derived container.

Canonical series hierarchies should stay within one concept by default. If a
proposed hierarchy edge appears to cross concepts, that should trigger explicit
review rather than being added automatically.

## Vintage and observation layer

### Observation

A single data point: a value for a series at a specific time period, from a
specific vintage (release).

Identified by `(series_id, period_start, vintage_date)` — these together are
UNIQUE. Two observations for the same series and period can exist only if they
come from different vintages.

`value` can be NULL — that's a "known gap," meaning the provider published a
release but the value for this period is intentionally missing. Different from
"never released," which is the absence of an observation row entirely.

### Vintage / vintage_date

The publication date of the release that the observation came from. When the
US BLS publishes the CPI report on the 15th of every month, that release date
is the vintage.

Series get revised: the value for January 2024 CPI as published in February 2024
may be revised when published again in March 2024. Both versions are stored as
separate observation rows with different `vintage_date` values. The
`latest_observations` view returns the most-recent vintage per
`(series_id, period_start)`.

### Snapshot vintage

A `vintage_date` assigned by macrodb on the day a latest-snapshot import was
observed, rather than a true provider-supplied release vintage.

This is the fallback model for providers or first-pass importers that do not
expose a usable historical vintage surface. In that mode, macrodb records
"what we observed on this run date" and accumulates a new observation row only
when a period is new or its value changed versus the latest stored snapshot.

A snapshot vintage is not the same thing as an archival provider vintage such
as an ALFRED real-time release date. When a provider exposes true vintage
history, that provider-native vintage should be preferred.

### Latest observations

A Postgres VIEW (not a table) defined as:

```sql
CREATE VIEW latest_observations AS
SELECT DISTINCT ON (series_id, period_start) *
FROM observations
ORDER BY series_id, period_start, vintage_date DESC;
```

This returns exactly one row per (series, period) — the highest vintage_date.
Use this for "current best estimate" reads. Use the raw `observations` table
for vintage analysis or backtests against historical releases.

### Period start / period end

`period_start` is the first day of the observation period; `period_end` is the
last. For monthly data, January 2024 has `period_start=2024-01-01` and
`period_end=2024-01-31`. For quarterly, Q1 2024 is `2024-01-01` / `2024-03-31`.

Stored as dates, not timestamps. `period_end >= period_start` is enforced by
CHECK.

## Provider layer

### Provider

An organization that publishes data. Examples: `World Bank`, `International
Monetary Fund`, `USA FRED`, `JPN e-Stat`, `Alpha Vantage`.

Identified by a unique `name`. Has a `type` (official, international_organization,
vendor, internal, other), homepage and doc URLs, an API base URL, and a
`credentials_ref` for managed secrets.

For country-scoped official publishers, the canonical provider `name` may
include a 3-letter geography prefix when that makes the source unambiguous.
Examples: `USA FRED`, `HKG Census and Statistics Department`, `JPN e-Stat`.
This is a naming convention, not a separate foreign-key field.

### Provider catalog

A sub-product of a provider. World Bank has multiple catalogs (WDI, Health
Nutrition and Population Statistics, etc.). FRED has effectively one catalog,
which is its full database — when a provider has no meaningful sub-catalogs,
the catalog has `is_placeholder=true`.

Provider catalogs are how we organize the "what data is available from this
provider" namespace. Provider-facing external codes often live in this catalog
namespace, but macrodb treats `series_sources.external_code` as nullable,
non-unique, best-effort metadata rather than as the extraction identity.

### Series source

The mapping from one of our `series` to one provider catalog's representation
of it. Contains the optional `external_code` (provider identifier, e.g.
`NY.GDP.MKTP.CD` in WDI or `CPIAUCSL` in FRED), an optional `external_name`,
an optional human-facing `ref_url` that points back to the relevant source page,
a `priority` (lower = preferred when multiple providers offer the same series),
and an optional `value_transform` (a JSONB recipe like `{"op": "divide", "by":
100}` for converting the provider's native scale to ours).

`external_code` is nullable but strongly encouraged as a best-effort
provider-facing locator for the logical series. For some providers it is a true
unique series code. For others, especially table-style or tree-style
statistical sources, it may be absent or may be a reused dataset code, table
code, or leaf label that is helpful for humans but not sufficient to
disambiguate extraction on its own.

The true extraction selector for shared multi-series payloads belongs on the
`ingestion_feed_member`, not on `series_source`.

`ref_url` is nullable but strongly encouraged. Multiple `series_sources` may
legitimately point to the same source page when one provider page or table
contains several logical series.

`provider_role` describes the relationship: `primary_source` (the canonical
publisher), `redistributor` (e.g. FRED carrying a BLS series), `harmonized`
(e.g. OECD's harmonized CPI), `vendor_estimate` (a vendor's proprietary estimate),
`internal`, or `other`.

### Ingestion feed

An ingestion feed is the runtime configuration for one upstream request shape or
execution unit. It may populate one or more `series_sources` through
`ingestion_feed_members`.

In the common case, a provider request still maps to a single `series_source`,
but some providers expose table-style or tree-style payloads where one upstream
request fans out into multiple logical series.

The feed owns shared request configuration: `feed_method` (`api`, `file`, or
`scrape`), endpoint URL, request params, response mapping, optional file path
pattern, and optional `cron_schedule` (metadata for an external scheduler —
**not** for `pg_cron`). It does not own the per-series extraction selector.

### Ingestion feed member

The attachment between a request-level `ingestion_feed` and one `series_source`.

An ingestion feed member carries the per-series extraction contract for how one
logical provider series is selected from the shared upstream payload produced by
the feed.

The extraction contract should be modeled as a small selector type plus
structured selector config, rather than as one universal fixed column set.
Different providers may need different selection shapes such as provider series
codes, dimension filters, table coordinates, tree node selectors, or other
structured path/filter rules.

One `ingestion_feed` may have many members. Each `series_source` belongs to
exactly one ingestion feed through exactly one member row.

An ingestion feed member may be active or inactive. A feed execution attempts
the active members attached to that feed at execution time.

An ingestion feed member may also carry an optional execution order so runtimes
that need deterministic processing can process members in a stable sequence.

The common provider case is still simple: one feed with one active member.
Shared table or tree requests use one feed with multiple active members.

### Ingestion run log

Append-only record of every attempt to run an ingestion feed.

Because an ingestion feed is the execution unit, the ingestion run log is also
feed-level rather than series-level. It captures started/finished timestamps,
status, row counts, error message, triggered_by, code version, runtime
parameters, and the overall outcome of one upstream request execution.

When one feed populates multiple `series_sources`, per-member success, failure,
and warnings belong in child records beneath the feed-level run log.

### Ingestion run log member

The per-execution outcome row for one `ingestion_feed_member` inside one
`ingestion_run_log`.

Member-level run rows capture success, failure, partial/warning outcomes,
row counts, and selector/parsing diagnostics for the logical series attempted
inside a shared feed execution. Active members should receive a member-level run
row even when they write zero observations, so attempted-no-op and not-attempted
remain distinguishable.

Observations produced by ingestion should link to the member-level run row that
created them. This is member-level provenance: a stored value points to the
exact logical extraction attempt, not merely the shared upstream request.

## Derivation layer

### Derived series

A series whose observations are computed from one or more input series, rather
than ingested from a provider. The `derived_series` row contains the
`formula_config` (JSONB recipe for the computation), description, execution
policy (scheduled / upstream_update / manual), determinism flag, vintage
awareness flag, and a `code_ref` pointing to the canonical Python function that
implements it.

Each `series` with `origin_type` of `derived` (or `both`) has exactly one row in
`derived_series` (enforced by `UNIQUE(series_id)`).

### Derivation input

A registry of which input series feed into which derived series. One row per
edge. The `notes` field is free-text for human-readable role (`minuend`,
`numerator`, `weight=0.3`). The structural specifics live in
`derived_series.formula_config`; this table is just the FK registry for lineage
analysis.

### Computation run log

Same shape as `ingestion_run_logs` but for derivations. Adds
`input_vintage_policy` (latest_available, vintage_as_of, fixed_vintage,
window_relative) and `output_mode` (write_observations, dry_run,
validation_only).

## Governance layer

### Change proposal

A proposed structural or data change to the system, possibly originating from
a user or from an AI agent. Has a status workflow: `proposed → approved →
applied`, or `rejected`, or `failed`, or `superseded`. Carries the `requested_by`
(user / agent / system), `created_by_agent` for agent-specific ID,
`user_prompt` (original ask), `rationale`, `risk_level`, and approval metadata.

### Change proposal item

The line items of a proposal. Each item is one concrete change: insert this
row, modify this file, run this test, etc. `target_type` identifies what kind
of entity (concepts, series, series_families, providers, geographies, etc., or
file/function/test). `action` is the operation. `proposed_data` carries the
content. `validation_status` tracks whether the item has been validated.

## Other terms

### Code

In macrodb, "code" almost always means the canonical short identifier of an
entity: `USA` for a geography, `CPI` for a concept, `US_CPI` for a family, etc.
Always UNIQUE within its table. The user-facing identifier; the UUID is internal.

### Prose field

A field that carries human-readable narrative rather than identity or
structural meaning. In macrodb the prose fields are `description` on
`concept`, `series_family`, and `series`; `name` on the same three; and
`variant` on `series_family_members`. Prose fields are read by humans
navigating the catalog. They are distinct from identity fields (`code`),
structural fields (enum-backed methodology columns like `frequency`,
`seasonal_adjustment`, `unit_code`), and provider-mapping fields
(`external_code`, `external_name` on `series_sources`).

Prose fields do not carry cross-row dependencies the way identity does,
so they are not protected by the publication boundary the way `code` is.
A description can be updated post-publication without endangering other
rows. The gated onboarding agent treats prose fields with their own
discipline: the agent may mutate most prose after Gate 1 approval, but
existing prose is grandfathered by default and only updated when one of
four narrow factual or outlier triggers fires. See ADR 0013 and
`docs/skills/skill-metadata-standardisation.md`.

### Enum gap

A condition encountered by the gated onboarding agent where a candidate
series' real-world methodology cannot be faithfully represented by the
existing values of one of macrodb's series-methodology enums
(`Frequency`, `SeasonalAdjustment`, `Measure`, `MeasureHorizon`,
`UnitKind`, `UnitScale`, `PriceBasis`, `ReferenceKind`,
`TemporalStockFlow`). The drafter emits an `EnumGapProposal`; the
session pauses at `enum_gap_wait`; the operator edits the Python
enum and writes an Alembic migration widening the named CHECK
constraint, applies it as `macrodb_owner`, and resumes the session.
On resume the graph verifies the value exists in both the Python
enum and the DB CHECK constraint before the drafter proceeds.

Enum gaps are distinct from **column gaps** (a methodological
distinction macrodb has not modelled at all, requiring a new
column). Column gaps abort the session with reason
`schema_deficiency` and are addressed in a separate operator-led
design pass.

The audit row for an enum gap lives in `change_proposals` with
`Action.suggest_enum_addition` and `TargetType.ENUM_VALUE`; its
lifecycle is independent of the session's main onboarding
proposal because the enum value, once committed, is reusable in
future sessions. See ADR 0014 and
`docs/skills/skill-enum-gap-escalation.md`.

### Credential gap

A condition encountered by the gated onboarding agent where a
candidate provider cannot be reached because authentication material
(typically an API key) is missing or invalid. The `research` role
runs a three-layer pre-check (existing `credentials_ref` lookup →
`os.environ` check → real probe) and emits a `CredentialGapProposal`
only when all three layers confirm the credential is required and
absent. The session pauses at `credential_gap_wait`; the operator
provisions the credential in their shell or secret store and resumes
the session. On resume the graph verifies via a fresh probe
(the truth) before research continues.

Credential gaps differ from **enum gaps** in three respects: detection
fires from `research` rather than `draft_proposal`; the picker offers
two options (Apply later, Abort) rather than three, because the probe
is ground truth and the override case routes through chat-level
Request changes if needed; and the provider-row write is **deferred
to Gate 1**, not committed at gap-apply time, because the gate
invariant says no catalog writes happen pre-Gate-1 and the credential
reference has no provider identity to attach to until then.

The agent never records the credential value. It is read from
`os.environ` at probe time and passed to the HTTP client. The audit
row records the env var name, the auth scheme, the rate limit
metadata, and the operator's rationale — never the value.

The audit row for a credential gap lives in `change_proposals` with
`Action.suggest_credential_provisioning` and
`TargetType.CREDENTIAL_REF`. Its lifecycle is independent of the
session's main onboarding proposal: a provisioned credential is real
operator-machine state regardless of whether the session ultimately
succeeds, and the audit row reflects that. See ADR 0016 and
`docs/skills/skill-credential-gap.md`.

### External code

The identifier used by a provider for a series. Lives on `series_sources`. Not
unique globally, but unique within a `provider_catalog`.

### Macrodb vs macro_foundry

`macro_foundry` is the system (the repo, the application). `macrodb` is the
database inside it. When discussing schema, tables, or migrations, use
`macrodb`. When discussing the application, the repo, the deploys, use
`macro_foundry`.

### Owner role vs app role

`macrodb_owner` is the DB role used by Alembic for migrations. `macrodb_app`
is the DB role used by FastAPI, SQLAdmin, ingestion (later), and tests.
Never mix them.

### Phase

A unit of build work, defined in `build_plan.md`. Phases 1–13. Phases are
sequential where they have dependencies and parallel otherwise. The
`progress_tracker.md` records phase completion.
