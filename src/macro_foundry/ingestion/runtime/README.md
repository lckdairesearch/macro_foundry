# Ingestion runtime — selector registry

This directory implements ADR 0012. It is the runtime that interprets
`IngestionFeed` and `IngestionFeedMember` rows at execution time and turns
upstream provider payloads into normalized observations.

Read ADR 0010 (request-level ingestion + canonical hierarchy) and ADR 0012
(this runtime) before touching anything here.

## What lives here

- `runner.py` — generic feed executor. Reads a feed, iterates its active
  members, dispatches each member to the appropriate `Selector` keyed by
  `selector_type`, writes the feed-level and member-level run log rows.
- `calendar.py` — frequency-driven period-bounds logic (extracted from the
  original FRED runner; now provider-agnostic).
- `selectors/` — the selector registry. One module per `selector_type`.

## The selector contract

Every selector implements the same interface:

| Member | Purpose |
|---|---|
| `name: str` | The string stored in `ingestion_feed_members.selector_type`. |
| `config_schema: dict` | JSON Schema describing valid `selector_config` shapes. Surfaced by the `macrodb-mcp` tool `get_selector_schema`. |
| `validate(config: dict) -> ValidationResult` | Static config validation. Called by `validate_selector_config` MCP tool and at runtime before any HTTP work. |
| `fetch(feed, member, http_client) -> RawPayload` | Performs the upstream request (or file read, or scrape) for one member. Selectors that share request shape across members of the same feed may cache at the feed level — `runner.py` exposes a feed-scoped cache. |
| `extract(payload, config) -> Iterable[ParsedObservation]` | Yields normalized observations: `(period_start, period_end, value, vintage_date | None)`. |
| `parse_provider_error(payload) -> ProviderErrorOrNone` | Defensive parsing for known error-vs-data wrapper patterns. If the provider returned a rate-limit notice, auth failure, or empty-data wrapper, this method recognizes it and the runner records a member-level failure with the provider's own message. |

`ParsedObservation` is `value | None` (NULL is "known gap"; missing
observation is "never released"; see `CONTEXT.md`).

## When an existing selector fits

Before drafting a new selector, check whether one of the existing selectors
covers the provider's shape:

- **`json_path`** — generic JSON-path-based extraction. Suits FRED, World Bank
  V2 API, Alpha Vantage, IMF SDMX-JSON, and any provider that returns a flat
  array of observation records under a stable JSON path.
- **`csv_column`** — for `feed_method = "file"` providers that publish CSV
  files. Suits BIS data downloads, BOJ Time-Series Search exports, and most
  national statistics offices that distribute CSVs.
- **`censtatd_json`** — for Hong Kong CenStatD. Knows about LZ-string param
  encoding and code-length-encoded hierarchies.
- **`estat_value_filter`** — for Japan e-Stat `getStatsData` responses. Knows
  about multi-dimensional `@catN` value filtering and e-Stat's bespoke time
  encoding.

If the provider fits, the agent writes only `selector_config` and catalog
rows. No Python is added.

## When a new selector is required

A new `selector_type` is justified when at least one of these is true:

- the provider uses a non-standard request encoding (compressed params,
  signed URLs, multi-step request flows)
- the response shape is nested in a way that JSON-path extraction cannot
  cleanly select one logical series at a time
- dimension semantics are encoded in string padding, prefix conventions, or
  magic values that need provider-specific interpretation
- the value field clashes with the JSON-path dialect (e.g., e-Stat's literal
  `$` key)
- the time field uses a bespoke encoding (e.g., e-Stat's
  `"YYYY000MM01"`)
- the provider returns error and data in different wrapper shapes and
  defensive parsing would otherwise live in every per-feed config

A new selector is **not** justified for one-off provider quirks that can be
expressed by extending an existing selector's config schema. Prefer extending
`json_path` over forking it.

## Sandbox-and-promote flow

The agent **never** writes to this directory directly during an onboarding
session. The sandbox path is `agent_workspace/proposed_selectors/<session_id>/`
at the repo root, gitignored.

Lifecycle:

1. **Draft.** The script drafter writes a new selector module to the sandbox.
   The module imports only from this package's public interface; it must not
   reach into `macro_foundry.models` or other application internals.
2. **Validate.** The validator runs the sandboxed selector against a probe
   payload captured during research. Parsed observations are surfaced for the
   data correctness reviewer.
3. **Review.** The selector reviewer reads the diff against
   `skill-ingestion-selector-conventions` and surfaces findings. The data
   correctness reviewer cross-references the parsed observations against the
   provider's published page or a reputable mirror.
4. **Gate 1.** The operator approves the catalog rows and the new selector
   as one bundle.
5. **Promote.** The executor's `apply_catalog` node copies the sandboxed
   module to `src/macro_foundry/ingestion/runtime/selectors/<name>.py`,
   registers it in `selectors/__init__.py`, runs the selector's own tests,
   and records the promotion in the run log.

Hard invariants:

- the agent never runs `git commit` or `git push`
- the agent never modifies files in `src/` outside the explicit promotion
  step
- the operator is the only commit author

If the operator declines promotion, the sandboxed selector stays in
`agent_workspace/` for inspection but is never registered or executed by
the runtime.

## Defensive parsing as a design discipline

Selectors must distinguish three response states clearly:

1. **Success with data.** Extract observations.
2. **Success with no data.** The provider acknowledged the request and
   returned an empty set (e.g., a feed for a series that hasn't published
   yet). Record a zero-row member-level run, not a failure.
3. **Failure presented as a 200 response.** Rate limits, auth failures, and
   provider-side error notices that arrive with HTTP 200 are common across
   macroeconomic APIs. Examples:
   - Alpha Vantage returns `{"Information": "..."}` or `{"Note": "..."}` for
     rate-limit and demo-key responses
   - e-Stat returns `GET_STATS_DATA.RESULT.STATUS != 0` for auth or query
     errors
   - World Bank returns a JSON array whose first element carries the error
     instead of the count
   Selectors must recognize these patterns in `parse_provider_error` and
   raise a member-level failure with the provider's own message. Silently
   writing zero rows is the worst outcome — it looks like success and rots
   the run log as a source of truth.

## Calendar and period semantics

`calendar.py` houses frequency-driven period-bounds logic. Every selector
that produces observations from a single anchor date plus a frequency uses
this module rather than implementing its own. The current contract:

- `period_bounds(anchor: date, frequency: Frequency) -> (period_start, period_end)`

The original FRED period-bounds logic lives here in canonical form. Provider
adapters add new frequencies only when no existing frequency matches, and
those additions are reviewed against `CONTEXT.md`'s frequency vocabulary.

## Snapshot vintage policy

The runtime follows the snapshot-vintage model described in `CONTEXT.md`. For
providers that do not expose true archival vintages, the runner assigns the
run's date as `vintage_date` and only writes a new observation row when the
period is new or its value changed since the previous snapshot. Providers
that expose archival vintages (FRED ALFRED, OECD's real-time database) should
use a selector that surfaces the provider-native vintage instead.

## Tests

Each selector ships with focused tests against recorded payload fixtures.
Tests cover:

- the happy path against the canonical provider shape
- defensive parsing against at least one known error wrapper
- empty-data handling
- a frequency or period-bounds edge case relevant to the provider

The generic `runner.py` has integration tests against a one-member feed and a
multi-member shared-payload feed, both using a stub selector to keep runner
tests independent of selector-specific HTTP details.

## Migration from `runners/fred_series.py`

The original `src/macro_foundry/ingestion/runners/fred_series.py` is to be
replaced by a feed with `selector_type = "json_path"` plus FRED's
`selector_config`. The migration steps are tracked separately in the
implementation phase; this README describes the destination, not the
intermediate state. Do not add new FRED code to `runners/`; new behavior
belongs in the generic runner plus an updated `json_path` selector.
