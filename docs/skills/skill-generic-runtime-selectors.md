---
status: stub
---
# skill-generic-runtime-selectors

**Status:** stub

## Scope

The currently registered `selector_type` values and the provider shapes
each one covers. Loaded by the researcher so the agent can answer "does
this provider fit an existing selector?" without operator help.

This skill is a *living index* of the selector registry. It is updated
whenever a new selector is promoted into
`src/macro_foundry/ingestion/runtime/selectors/`. It does not cover the
selector contract itself (see
[skill-ingestion-selector-conventions](skill-ingestion-selector-conventions.md))
or the decision rules about when to add a new selector.

## When triggered

- node is `research` (during provider-shape evaluation)
- node is `draft_proposal` (to confirm `extraction_mode` and pick a
  selector)

## Body

To be written. Should enumerate each registered selector with:

- the `selector_type` string
- a one-sentence description of the provider shape it expects
- the canonical example provider(s) it covers
- the required and optional fields in `selector_config`
- the response patterns it parses as provider errors

Initial registry entries to document once the runtime is built:
`json_path`, `csv_column`, `censtatd_json`, `estat_value_filter`.

The body of this skill should be kept short and example-driven. The
detailed schemas live in each selector's `config_schema` and are
discoverable via the MCP tool `get_selector_schema(selector_type)`.
