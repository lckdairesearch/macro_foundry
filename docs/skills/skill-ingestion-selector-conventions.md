# skill-ingestion-selector-conventions

**Status:** stub

## Scope

The selector contract, naming conventions, defensive-parsing discipline,
and code review criteria for new `selector_type` extensions in the
ingestion runtime. Pulls from ADR 0012 and
`src/macro_foundry/ingestion/runtime/README.md`.

This skill is loaded by the selector reviewer and by the script drafter
when drafting a new selector. It does not cover *which* selector to use
for a given provider (see
[skill-generic-runtime-selectors](skill-generic-runtime-selectors.md)) or
the decision to add a new selector at all (covered by ADR 0012's "when an
existing selector fits" section).

## When triggered

- node is `script_drafter` or `selector_review`
- `state.extraction_mode == "custom_python"`

## Body

To be written. Should cover: the required selector interface (`name`,
`config_schema`, `validate`, `fetch`, `extract`, `parse_provider_error`);
the JSON Schema conventions for `config_schema`; the
defensive-parsing requirement (success-with-data vs. success-with-no-data
vs. provider-error-as-200 must be distinguishable); the use of
`runtime/calendar.py` for period bounds rather than reimplementing per
provider; the prohibition against reaching into `macro_foundry.models`
from selector code; the test expectations (happy path, defensive parse,
empty data, period-bound edge); and the naming convention
(`<provider_short_id>_<shape>`).
