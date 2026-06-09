# Series Onboarding Workflow

This document defines the interactive gated workflow for onboarding new data
sources and new canonical series into macrodb.

It is intentionally separate from `docs/series_catalog_governance.md`:

- `series_catalog_governance.md` governs canonical identity and `series.code`
- this document governs the multi-step onboarding process and approval gates

## Purpose

The onboarding process should be interactive, not a fire-and-forget agent task.
The system should favor proposal, review, and controlled test execution over
silent catalog mutation.

This workflow is designed to support both:

- a human-assisted operating mode today
- a future LangGraph implementation with explicit state, retries, and approval
  interrupts

## Default shape

Normal path:

1. researcher agent investigates the source and existing macrodb state
2. reviewer agent checks the proposal for factual, schema, and governance fit
3. human approves Gate 1
4. executor agent applies approved catalog/feed changes in the test database
5. executor agent runs and monitors the first real ingestion in the test database
6. human reviews the test outcome and either accepts the onboarding package as
   test-approved or sends it back for refinement

Dangerous correction path:

1. researcher agent detects a published-series identity problem
2. reviewer agent checks the diagnosis and impact
3. human reviews the dangerous correction proposal
4. executor agent applies only the approved repair plan

## Roles

### Researcher agent

The researcher agent may:

- gather source background information
- inspect existing DB state
- run probe fetches and normalization samples
- draft or refine a proposal
- suggest likely interpretations when metadata is ambiguous

The researcher agent should not auto-create canonical catalog rows when
identity-level ambiguity remains unresolved.

### Reviewer agent

The reviewer agent is read-only with respect to catalog and observation data.

The reviewer agent may:

- inspect the source, DB state, and proposal
- fact-check the researcher's claims
- check schema fit and naming/governance fit
- update workflow state such as findings, flags, status, and retry count
- request refinement from the researcher agent

The reviewer agent must not:

- create or modify canonical series
- create or modify sources or feeds
- write observations

Review loop policy:

- reviewer may bounce the proposal back to the researcher
- maximum: 3 review cycles
- if the proposal still fails review after 3 cycles, escalate to the human gate

### Executor agent

The executor agent performs approved writes only after the required human gate.

The executor agent may:

- create or update approved catalog rows
- create or update approved source/feed rows
- run the first real ingestion
- monitor run progress and outcome
- report warnings, failures, and test-review readiness

## Gate policy

### Gate 1: onboarding approval

This is the default human gate before any catalog or feed mutation.

The proposal should summarize:

- what already exists
- what new rows would be created or updated
- where ambiguity was found
- what assumptions were made
- whether derived series are suggested
- the expected first-ingestion behavior

### Gate 2: dangerous correction approval

This gate is required for identity corrections to published canonical series.

Typical triggers:

- a published series is later discovered to be underspecified
- the wrong canonical variant was created
- source/feed mappings need reassignment because canonical identity was wrong

## Hierarchy enrichment review

Onboarding should surface likely child-series additions as additive hierarchy
enrichment. If source research finds a provider table, tree node, or release
detail that appears to sit below an existing canonical parent series, the
researcher should include the proposed hierarchy edge in the onboarding package
instead of letting ingestion create structure as a side effect.

The same-concept default is that proposed `series_hierarchy_edges` stay within
one concept unless the reviewer and human gate explicitly approve a
cross-concept hierarchy proposal. A cross-concept hierarchy proposal is a
governance flag, not routine ingestion work.

Human review expectations:

- confirm the parent and child are real canonical `series` rows
- confirm no hidden placeholder canonical series is being created only to mimic
  provider indentation
- confirm the parent observations remain independent published values
- approve any new hierarchy edge through onboarding or repair before it is
  written

Weak provider locator review:

Missing or weak provider-facing locators are review concerns even when the
schema allows nulls. Flag a weak provider locator when a source has missing
`external_code`, a reused dataset or table code instead of a leaf identifier, an
ambiguous provider label, missing `ref_url`, or a URL that points only to a
broad portal instead of an inspectable source page.

## Ambiguity rule

If ambiguity affects canonical identity, the workflow stays in proposal space.

That means the system may:

- research
- probe
- compare against the current catalog
- refine a proposal

But it should not create a draft canonical `series` row in the main catalog
until the ambiguity is resolved by review and approval.

Minor uncertainty should not automatically block progress. The agent should make
reasonable best-effort inferences and flag what matters, not over-escalate every
imperfect metadata field.

## Default variants

Not every provider-exposed qualifier must become part of canonical identity.

Some families may have a curated default variant whose omitted qualifier is
understood inside the project. This should still be checked during review when a
new source could plausibly point to a narrower sibling variant.

If the reviewer cannot tell whether the source refers to the default variant or
to a distinct sibling, the workflow should stay in proposal space.

## First real ingestion policy

The first real ingestion is special and should be treated as a monitored
bootstrap/backfill run, not as an ordinary incremental refresh.

Requirements:

- run first in the test database
- monitor the run rather than fire-and-forget
- treat the first run as an initial full-history or broad backfill ingest,
  ideally as far back as the source supports
- tolerate provider coverage starting later than the requested backfill date
- record warnings when the requested start date is earlier than actual provider
  coverage

The first run should fail when trust in identity or data integrity is in doubt,
not merely because the provider has less history than requested.

Examples of tolerated first-run warnings:

- requested start date is before provider coverage begins
- older periods are absent because the provider never published them
- the backfill completes successfully but from a later start date than requested

Examples of first-run failures:

- the source appears to map to the wrong canonical series
- provider metadata and canonical identity materially disagree
- parsing cannot derive trustworthy period bounds
- auth/config/runtime errors make the run result untrustworthy

## Incremental policy after bootstrap

After the first test-approved backfill run, later scheduled or manual refreshes
should usually switch to incremental overlap-window fetches rather than full
history pulls.

This follows the same latest-snapshot model already documented for the FRED
bootstrap plan:

- bootstrap/backfill can be broad or full-history
- subsequent runs fetch an overlap window plus newer periods
- unchanged periods do not create new observation rows
- changed periods create new snapshot-vintage observations

Routine refreshes must not create, delete, or rewrite `series_hierarchy_edges`.
Structural hierarchy changes belong in an explicit onboarding or approved
repair flow, not in scheduled or manual refresh execution.

## Deferred deployment workflow

Promotion beyond the test-approved onboarding package is intentionally out of
scope for this document.

`dev -> prod` should be handled later as a separate outer deployment workflow or
promotion graph.

This document stops at:

- approved catalog/feed setup in `test`
- a monitored initial test ingestion
- human review of the test result

## Output artifact

This workflow should end by producing a durable test-approved onboarding
package.

That package is the handoff boundary between:

- this onboarding graph
- a later outer deployment or promotion workflow

Minimum contents:

- approved proposal summary
- the canonical rows created or updated in `test`
- reviewer findings, flags, and final status
- first-run ingestion summary
- warnings or tolerated issues recorded during the initial backfill
- explicit status that the package is `test-approved`

## LangGraph fit

This workflow is a graph, not a simple linear chain.

Why:

- reviewer may reject and send back for refinement
- ambiguity may hold the flow in proposal space
- the first ingestion run needs monitoring and possible adaptive handling
- dangerous corrections need a different branch from ordinary onboarding
- human approval interrupts are part of the design

Recommended node classes:

- source research
- DB gap check
- probe fetch and normalization
- proposal drafting
- review
- human approval wait
- approved apply
- first-run monitoring
- test-result review
- onboarding-package emit
- dangerous correction planning

## Implementation note

The future implementation will likely benefit from MCP access to Postgres so
the agents can inspect existing catalog state without loading broad application
context.

Helpers or skills should stay narrow and context-efficient. Prefer small units
such as catalog lookup, proposal drafting, review, and correction impact
analysis over one giant onboarding prompt.

The likely next workflow layer after this document is a separate deployment or
promotion graph for moving a test-approved onboarding package into later
environments.
