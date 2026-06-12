# FRED Bootstrap Plan

This document records the agreed first-pass implementation plan for a curated
FRED stress-test bootstrap. It exists so a fresh agent can implement the work
without reconstructing the design discussion.

## Goal

Prove that macrodb can:

- create curated concepts, families, series, sources, and feeds for a small
  U.S. macro preset
- ingest raw latest-snapshot observations from FRED
- write ingestion outputs into the database in a rerunnable way

This is intentionally a narrow preset bootstrap, not a general ingestion
framework.

Derived series (YoY, QoQ, etc.) are explicitly out of scope for this first
pass. They will be added later as a separate workflow, not bundled into the
bootstrap.

## Out of scope for first pass

- full ALFRED archival vintage history
- provider-native historical release-vintage reconstruction
- a generic arbitrary-series importer
- non-FRED providers
- bucket-hosted scripts or executable code stored in the database

## Command shape

First-pass UX:

`macrodb db bootstrap fred-us-macro --target test`

Behavioral rules:

- the command is separate from `macrodb seed`
- the command must accept an explicit environment target
- the implementation should support `dev` and `test`
- implementation work should be exercised against `macrodb_test` first
- default target should remain `dev`; `--target test` is an explicit safety
  switch during development

## Runtime/code placement

Implementation should live in committed repo Python modules.

Recommended seams:

- `src/macro_foundry/ingestion/providers/fred.py`
- `src/macro_foundry/ingestion/runners/fred_series.py`
- bootstrap orchestration under package code, surfaced through the Typer CLI

The database stores feed configuration and code references. It does not store
script bodies.

## Environment and credentials

Use `FRED_API_KEY` from the environment.

`.env.example` should be updated to include `FRED_API_KEY`.

No code should read or depend on `ALPHA_VANTAGE_API_KEY` for this work.

## Provider/catalog/source policy

For this first preset:

- provider: `USA FRED`
- provider catalog: `FRED default catalog`
- `provider_role`: `redistributor`
- `priority`: `1`

Rationale:

- FRED is the operational fetch surface for this first stress test
- canonical provenance beyond that is deferred
- provider tickers remain in `series_sources.external_code`

## Schedule metadata

All first-pass FRED ingestion feeds should store:

`TZ=America/New_York 0 8 * * *`

This is metadata for a future external scheduler, not an instruction to run
inside the database.

## Curated preset contents

### Concepts

- `GDP`
- `CPI`

### Geographies

- existing seeded `USA`

### Series families

- `US_GDP`
- `US_CPI`

### Raw ingested series

These are level series. Per `docs/series_catalog_governance.md`, level
canonical codes omit the measure slot, so no `_LEVEL` suffix:

- `US_GDP_NOMINAL_Q_SAAR`
- `US_GDP_REAL_Q_SAAR`
- `US_CPI_HEADLINE_M_NSA`
- `US_CPI_CORE_M_SA`

## Raw FRED mappings

The first preset should wire these external codes:

- `GDP` -> `US_GDP_NOMINAL_Q_SAAR`
- `GDPC1` -> `US_GDP_REAL_Q_SAAR`
- `CPIAUCNS` -> `US_CPI_HEADLINE_M_NSA`
- `CPILFESL` -> `US_CPI_CORE_M_SA`

Metadata confirmed from official FRED series pages:

- `GDP`: quarterly, billions of dollars, seasonally adjusted annual rate
- `GDPC1`: quarterly, billions of chained 2017 dollars, seasonally adjusted
  annual rate
- `CPIAUCNS`: monthly, index 1982-1984=100, not seasonally adjusted
- `CPILFESL`: monthly, index 1982-1984=100, seasonally adjusted

Implementation should still inspect real API payloads and series metadata while
coding. The period-bound logic should live in provider-specific ingestion code,
because economic providers format time periods differently.

## Latest-snapshot ingestion policy

The first pass uses a latest-snapshot model, not true archival vintages.

Initial bootstrap run:

- fetch full latest snapshot history for each raw series
- write all rows with `vintage_date = run_date`

Incremental scheduled runs after bootstrap:

- fetch an overlap window plus newer periods
- compare each fetched period against the latest stored observation for that
  `series_id` and `period_start`
- if the period is new, insert a new observation with `vintage_date = run_date`
- if the period exists and the value changed, insert a new observation with
  `vintage_date = run_date`
- if the period exists and the value is identical, write nothing
- do not delete prior observations on incremental runs

Routine FRED refreshes must not mutate hierarchy structure. They may read
existing `series_hierarchy_edges` for reporting in later work, but they must not
create, delete, or rewrite hierarchy edges. If FRED research reveals a likely
new child relationship, structural changes belong in onboarding or approved
repair workflows.

This yields macrodb-observed snapshot vintages from the day tracking started.
It is explicitly different from true ALFRED release-vintage history.

## Overlap window policy

Overlap windows should be:

- defined by provider/frequency defaults in repo code
- overridable per feed in `ingestion_feeds.request_params`
- omitted from `request_params` when a feed uses the provider default

Recommended first-pass defaults:

- monthly: 18 months
- quarterly: 8 quarters
- annual: 5 years
- weekly: 12 weeks
- daily: 35 days

Suggested override shape in `request_params`:

```json
{
  "series_id": "GDP",
  "overlap": {
    "unit": "quarters",
    "value": 8
  }
}
```

## Period mapping policy

`period_start` and `period_end` should be derived inside the FRED adapter from
actual incoming payloads plus known series frequency.

Rules:

- do not hard-code one universal date-mapping rule at the database layer
- use provider-specific parsing logic
- preserve the provider date as the anchor for `period_start`
- derive `period_end` from the period semantics of the series being ingested

For this preset, expected frequencies are monthly CPI and quarterly GDP, but the
implementation should still inspect the real response rather than assuming all
providers behave like FRED.

## Derived-series policy

Out of scope for this preset. The schema layer still supports derivations
(`derived_series`, `derivation_inputs`, `computation_run_log` per
`CONTEXT.md`), but the FRED bootstrap registers and ingests level series
only. A later workflow will register and compute derived series against the
ingested levels.

## Suggested implementation order

1. Update `.env.example` with `FRED_API_KEY`.
2. Add any bootstrap CLI surface needed.
3. Implement the FRED provider client and provider-specific period parsing.
4. Implement catalog upsert/orchestration for the curated preset.
5. Implement raw latest-snapshot observation ingest with run-log recording.
6. Add tests around:
   - bootstrap catalog creation
   - first-run observation import
   - incremental rerun with unchanged data
   - incremental rerun with changed data

## References

- `CONTEXT.md`
- `docs/series_catalog_governance.md`
- this file
