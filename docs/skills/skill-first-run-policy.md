---
status: stub
---
# skill-first-run-policy

**Status:** stub

## Scope

The "tolerated warnings vs. hard failures" rules for the first ingestion
run after a Gate 1 approval. Covers the broad-backfill default, the
provider-coverage tolerance, and the categorical failures that should
abort the test-approval flow regardless of how much data was written.
Pulls from the "First real ingestion policy" section of
`docs/series_onboarding_workflow.md`.

This skill does not cover incremental refresh policy after bootstrap
(that lives in the workflow doc directly) or the monitor node's polling
mechanics.

## When triggered

- node is `monitor_first_run` or `test_review`
- `state.first_run_status` is non-null

## Body

To be written. Should cover: the broad-backfill default and how to derive
"as far back as the source supports" per provider; the tolerance for
provider-coverage starting later than requested; the categorical
failures (wrong canonical series, metadata-vs-identity disagreement,
period-bound parsing failures, auth or config errors); the language for
synthesizing first-run outcomes into a human-readable test-review summary;
and the boundary between "succeeded with warnings" and "failed" status.
