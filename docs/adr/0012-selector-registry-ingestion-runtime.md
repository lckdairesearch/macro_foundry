# ADR 0012 - Selector-registry ingestion runtime

**Status:** Accepted

**Date:** 2026-06-10

## Context

ADR 0010 redefined `ingestion_feed` as a request-level execution unit and
added `ingestion_feed_member.selector_type` plus `selector_config` as the
per-series extraction contract. The schema was designed for a generic
runtime that interprets selectors at execution time. The runtime to do that
interpretation does not yet exist; the current FRED runner
(`src/macro_foundry/ingestion/runners/fred_series.py`) is a custom Python
module that hard-codes FRED's request shape, frequency parsing, and period
bounds, and records `selector_type` only as a diagnostic.

Extending the codebase one bespoke Python module per provider does not scale.
Macrodb intends to onboard tens of providers across many countries, each with
different request encodings, response shapes, dimension semantics, and quirks.
At the same time, "pure config, no Python" is not achievable: stress-testing
real provider responses (e-Stat, Hong Kong CenStatD) showed that some
providers require provider-specific request encoding (LZ-string compressed
params), bespoke time encodings, multi-dimensional value filtering, and
defensive parsing of error-vs-data response wrappers that no generic JSON-path
selector can express in config alone.

The schema is correct. The runtime needs to honor it.

## Decision

Build a selector-registry ingestion runtime in
`src/macro_foundry/ingestion/runtime/` that interprets feed and member
configuration at execution time. The unit of Python is the `selector_type`,
not the feed.

**Runtime structure.**

```
src/macro_foundry/ingestion/runtime/
├── README.md           # selector contract, sandbox/promote guide
├── runner.py           # generic feed executor
├── calendar.py         # frequency-driven period-bounds logic
└── selectors/
    ├── __init__.py     # registry
    ├── json_path.py    # generic JSON path-based extraction
    ├── csv_column.py   # for file-method feeds
    ├── censtatd_json.py    # HK CenStatD: LZ-string params + code-length hierarchy
    └── estat_value_filter.py  # JPN e-Stat: multi-dimensional value filtering
```

`runner.py` reads `IngestionFeed` plus its active `IngestionFeedMember` rows,
dispatches to the appropriate `Selector` keyed by `selector_type` for each
member, and writes feed-level and member-level run log rows per the existing
schema. `calendar.py` houses frequency-to-period-bounds logic extracted from
the current FRED runner and made provider-agnostic.

**Selector contract.** Each selector implements:

- a `name` matching `selector_type` values stored in the database
- a `config_schema` as JSON Schema, retrievable via the MCP server for agent
  consumption
- a `validate(config: dict) -> ValidationResult` for static config validation
- an `extract(payload, config) -> Iterable[ParsedObservation]` that yields
  normalized observations
- defensive parsing for known error-vs-data wrapper patterns (e.g., Alpha
  Vantage `Information` notices, e-Stat error responses)

**Adding a new selector_type is a deliberate, reviewed event.** Selectors are
not authored ad-hoc per feed. The gated onboarding workflow's script drafter
writes proposed selectors to
`agent_workspace/proposed_selectors/<session_id>/` (gitignored). The selector
reviewer reviews against `skill-ingestion-selector-conventions`. The executor
promotes approved selectors into `src/macro_foundry/ingestion/runtime/selectors/`
as part of the same gate approval that approves catalog rows. See ADR 0011
and `docs/series_onboarding_workflow.md` for the lifecycle.

**Migration of FRED.** The existing `fred_series.py` runner is replaced by a
generic-runner invocation against a feed with `selector_type = "json_path"`
and a `selector_config` that expresses FRED's metadata endpoint, observations
path, period anchor field, value field, missing-value tokens, and frequency
map. The FRED-specific period-bounds logic moves into `calendar.py` as
provider-agnostic frequency utilities.

**MCP tools.** The custom `macrodb-mcp` server exposes
`list_selector_types()`, `get_selector_schema(selector_type)`, and
`validate_selector_config(selector_type, config, sample_payload)` so the agent
can discover selectors and validate configs without bespoke prompts.

## Consequences

**Positive:**

- The schema designed by ADR 0010 is honored by code. `selector_type` and
  `selector_config` become functional, not descriptive metadata.
- Most new feeds for a given provider need only config, not Python. After the
  one-time cost of adding a provider-specific selector, every additional
  series under that provider is config-only.
- Generic selectors (`json_path`, `csv_column`) cover an estimated ~40% of
  new feeds outright; provider-specific selectors are written once per
  provider, not once per feed. The selector library is bounded by unique
  provider API designs, not by feeds × countries × concepts.
- Defensive parsing is centralized in selector code rather than scattered in
  per-feed scripts. Patterns like "rate-limit wrapper masquerading as data"
  are addressed once per selector.
- The agent's catalog of capabilities is discoverable: `list_selector_types`
  tells the agent what shapes are already supported, so the agent's research
  phase can confidently identify when a new selector is needed.
- New providers are added to the runtime in a single, reviewable diff
  (one new selector module), not by amending many per-feed runners.

**Negative:**

- Adds upfront work that did not exist before the agent: the runner, the
  selector registry, the calendar utilities, the migration of FRED off
  `fred_series.py`. This is real refactor scope and must land before the agent
  can usefully target ingestion.
- `IngestionFeed.endpoint_url`, `request_params`, `response_mapping`, and
  `file_path_pattern` semantics must be sharpened to match what the generic
  runner expects. Feeds authored against the current FRED runner will need
  updating during the migration.
- The selector registry becomes a small but important shared dependency
  across the codebase. A selector with a bug affects every feed that uses
  it, not just one feed.
- New `selector_type` extensions require the full gated onboarding flow
  (sandbox, validation, selector reviewer, gate approval, promotion). This
  is the right safety property, but it adds steps for the gnarly providers
  it most applies to.
- Tests must cover both the runner and individual selectors. A `json_path`
  selector test against a FRED-shape payload, a `csv_column` selector test
  against a file fixture, and a `censtatd_json` selector test against a
  recorded HK response are all required to keep parity with the current FRED
  test coverage during and after migration.

## Alternatives considered

- **One Python module per provider (current shape).** Rejected because it does
  not scale across tens of providers, duplicates request/response logic that
  is actually shared (period bounds, missing-value semantics, defensive
  parsing), and contradicts ADR 0010's "the data model must not assume
  one-request-one-series" principle.
- **One Python module per feed, agent-authored.** Rejected because the unit
  of Python should match the unit of upstream API shape, which is the
  provider, not the feed. Per-feed Python compounds rather than shares the
  per-provider quirks.
- **Pure config with no Python ever.** Rejected after stress-testing real
  responses. Providers with LZ-string compressed query params, bespoke time
  encodings, multi-dimensional dimension filtering, or
  CLASS_INF-style metadata lookup cannot be expressed in plain
  selector_config against a generic JSON-path runtime. Insisting on
  config-only would push the unmodeled complexity into either the agent's
  prompt or the catalog itself, neither of which is the right home.
- **Generic third-party ETL framework (Singer, Meltano, dlt).** Rejected
  because the runtime needs to compose with macrodb's existing
  `IngestionFeed`, `IngestionFeedMember`, `IngestionRunLog`, and
  `IngestionRunLogMember` shapes; the snapshot-vintage semantics; and the
  member-level observation provenance from ADR 0010. Adopting a generic
  framework would require either bending macrodb's schema toward the
  framework's model or maintaining a thicker adapter than the runtime would
  itself be. Building the runtime in-repo keeps the schema as the source of
  truth.
- **Agent edits per-provider Python directly in `src/`.** Rejected because
  the hard invariant "agent never commits or pushes code" requires a
  sandbox-and-promote pattern. Direct edits also make every onboarding
  session a potential codebase modification, which conflates governance
  artifacts with code review and breaks the workflow doc's safety model.
