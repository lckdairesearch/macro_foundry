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

This workflow is implemented as a LangGraph state machine driven by a chat-style
CLI session. The CLI is a foreground process: it starts on demand, persists
graph state to a Postgres checkpointer, and exits cleanly when the operator
saves or closes the session. There is no daemon and no idle compute between
sessions.

## Default shape

Normal path:

1. researcher agent investigates the source and existing macrodb state, doing
   web research and probe fetches as needed
2. proposal drafter assembles a draft catalog + selector-config proposal
3. script drafter produces a sandboxed `selector_type` extension when no
   existing selector covers the provider; skipped otherwise
4. validator runs the selector against a sample payload and reports parsed
   observations for review
5. three reviewers run in parallel: governance, data correctness, selector code
6. human approves Gate 1
7. executor applies approved catalog/feed rows to the staging database and
   promotes any approved selector extension into the runtime registry
8. executor triggers the first ingestion run
9. monitor node polls the run to terminal status; resumable across session
   pauses
10. human reviews the first-run outcome and either accepts the onboarding
    package as test-approved or sends it back for refinement

Dangerous correction path:

1. researcher detects a published-series identity problem, or an onboarding
   session encounters a uniqueness collision that the operator chooses to
   challenge rather than rename around
2. dangerous correction planner drafts an impact analysis and a repair plan
3. reviewers check the diagnosis, impact, and proposed repair
4. human reviews and approves Gate 2
5. executor applies only the approved repair plan

## Roles

### Researcher

The researcher may:

- gather source background information using web search and web fetch
- inspect existing DB state via the read-only `macrodb-mcp` tool surface
- run probe fetches and normalization samples against the candidate provider
- draft or refine an `OnboardingIntent` and seed `source_summary` for
  downstream nodes
- suggest likely interpretations when metadata is ambiguous

The researcher must explicitly flag provider weirdness during research:
non-standard request encoding (compressed params, bespoke auth flows), response
wrappers that differ between data and error states, dimension semantics encoded
in code padding or magic values, mixed-type fields, multi-language fields, and
pagination quirks. These are the signals that an existing `selector_type` does
not fit and that a new selector extension may be required.

The researcher must not auto-create canonical catalog rows when identity-level
ambiguity remains unresolved.

### Proposal drafter

The proposal drafter consumes research findings, the `reference_metadata`
state field populated by `gather_reference_metadata`, and the
`extraction_mode` state field populated by `classify_extraction_mode`, and
produces a `DraftProposal` covering candidate concept, family, series,
source, feed, member, and hierarchy edge rows. It is read-only with
respect to the database; its output is a proposal in graph state, not a
write.

When writing prose fields (`description`, `name`, `variant`) the drafter
must anchor on `reference_metadata` per
[skill-metadata-standardisation](skills/skill-metadata-standardisation.md).
The drafter never writes prose blind.

The drafter may emit a harmonisation side-output: a list of proposed
updates to prose fields on **existing** series, when the new prose under
draft reveals that an existing sibling or cohort entry fires one of the
four closed harmonisation triggers (`factual_incompleteness`,
`factual_error`, `family_outlier`, `house_voice_outlier`). These items
ride along on the same Gate 1 proposal as the new series and are
governed by the metadata-standardisation skill; the default is to emit
nothing.

For propose-only fields (`concept.name`, `indicators.name`, all
`*.code` values), the drafter emits items with
`action = suggest_human_apply`. The executor skips these at apply
time; they remain in `change_proposals` as `pending_human_apply` until
the operator marks them applied in SQLAdmin.

For structural enum-backed fields the drafter does **not** emit
`suggest_human_apply`. Instead, when a candidate series' methodology
cannot be represented by any existing value of an allowlisted
series-methodology enum, the drafter emits one or more
`EnumGapProposal` items on its `enum_gap_proposals` output and
blocks. The graph routes to `enum_gap_wait` for an operator pause /
apply / resume cycle. See `Enum-gap escalation` below and
[ADR 0014](adr/0014-enum-gap-escalation.md).

### Script drafter

The script drafter only runs when `extraction_mode == "custom_python"`. It
produces a proposed new `selector_type` extension as a Python module in the
sandbox at `agent_workspace/proposed_selectors/<session_id>/`. It never
modifies the main codebase. See `Script lifecycle` below.

### Validator

The validator executes the proposed selector (existing or sandboxed) against a
probe payload from the provider and reports parsed observations. It populates
`validation_result` for downstream review. Failures here loop back to the
relevant drafter.

### Reviewers

The reviewer role is split into **two specializations**, each read-only
with respect to catalog and observation data. They run in parallel after
drafting and validation; their findings are merged before Gate 1. See
[ADR 0015](adr/0015-reviewer-role-consolidation.md) for the rationale
behind consolidating from three roles to two.

**Governance reviewer.** Checks schema fit, code-grammar conformance,
concept vs. family vs. variant boundaries, hierarchy edge governance
(same-concept default, no hidden placeholders), and provider locator
quality. Reviews harmonisation items against the four closed triggers
(ADR 0013) and `EnumGapProposal` items against the three conditions plus
anti-pattern list (ADR 0014). When `extraction_mode == custom_python`,
conditionally loads `skill-ingestion-selector-conventions` to review the
sandboxed selector module as part of the same call, and the router sets
`task_hint = "selector_code_review"` to route to a code-reviewing model
configured in the role's `models_by_task` map. Selector code review is
therefore a specialty *inside* governance, not a separate role.

**Data correctness reviewer.** Inspects the validator's parsed sample
observations against expected magnitude bands, frequency, period
boundaries, and unit conventions for the concept. Uses web search and
web fetch to cross-reference at least one recent observation against the
provider's own published page or a reputable mirror. Loads
`skill-macro-research-discipline` and concept-plausibility skills.

Both reviewers must not:

- create or modify canonical series
- create or modify sources or feeds
- write observations
- commit or push code

Read-only enforcement is structural, not prompt discipline: read-only
reviewer roles bind to the read-only `macrodb-mcp` instance, which does
not expose write tools. Folding selector code review into governance
does not weaken this guarantee.

Review loop policy:

- a reviewer may bounce the proposal back to the relevant drafter
- soft cap: 3 review cycles
- the gate prompt at cycle 3 explicitly offers the human three options:
  approve as-is, reject, or permit a further refinement cycle

### Executor

The executor performs approved writes only after the required human gate. Its
work is split across three resumable nodes to keep idempotency clear on
crash-and-resume:

- **`apply_catalog`** — writes approved catalog/feed rows transactionally via
  the write-enabled `macrodb-mcp` instance; promotes any approved selector
  extension out of the sandbox into the runtime registry
- **`trigger_first_run`** — instructs the ingestion runner to execute the new
  feed and records the resulting `ingestion_run_log` row
- **`monitor_first_run`** — polls the run log to terminal status; survives
  session pauses by re-querying status on resume

The executor must report warnings, failures, and test-review readiness, and
must never commit or push code to the repository.

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
- companion harmonisation items, if any (updates to prose fields on
  existing series, separated visually from the new-series items)
- propose-only items, if any (`suggest_human_apply` rows the executor
  will not touch, listed separately so the operator sees what they are
  expected to apply later via SQLAdmin)

The approval picker covers the whole bundle. To accept the new series
but drop the harmonisation items (or vice versa), use the
`Request changes` path; item-level approval checkboxes are not part of
the picker.

### Gate 2: dangerous correction approval

This gate is required for identity corrections to published canonical series.

Typical triggers:

- a published series is later discovered to be underspecified
- the wrong canonical variant was created
- source/feed mappings need reassignment because canonical identity was wrong
- an onboarding session encounters a uniqueness collision on a canonical code
  and the operator chooses to challenge the existing series identity rather
  than rename the new proposal

### Approval semantics

Both gates use the same structured approval signal: a Questionary picker with
`Approve`, `Reject`, and `Request changes` options, rendered beneath the
proposal summary. The picker is the high-stakes signal; the chat input remains
available for free-text alongside the picker for context or extracted change
descriptions.

The structural picker decides routing. An LLM only does extraction inside the
`Request changes` branch (parsing the free text into concrete edit
instructions), never classification at the gate itself. This keeps approval
auditable as a deliberate operator action, not as a chat interpretation.

Un-approval window: between picking `Approve` and the executor actually
committing rows, the operator may revoke approval. Post-commit, revocation
becomes a correction proposal, not a revocation.

### Small textual edits

When the operator picks `Request changes` with a small textual edit (e.g.,
"change the concept code to `EFFECTIVE_YIELD`"), the system applies the edit
to the in-memory proposal and runs a uniqueness pre-check against the staging
database for every column the schema marks UNIQUE that was touched. The
reviewers do not re-run for textual edits.

If no collision is detected, the updated summary is re-rendered and the gate
picker is re-issued.

If a collision is detected, the operator is offered a structured three-way
choice:

- pick a different code (returns to the small-edit subflow)
- treat the existing series as wrong and branch into the Gate 2
  dangerous-correction flow
- cancel the change and keep the original proposal

Structural edits (changes to series methodology, hierarchy edges, selector
configuration, etc.) route back through the full drafter and reviewer cycle,
not the small-edit subflow.

## Metadata standardisation

The drafter is responsible for keeping prose fields (`description`,
`name`, `variant`) consistent across related series without producing
cosmetic churn on existing prose. The discipline lives in
[skill-metadata-standardisation](skills/skill-metadata-standardisation.md);
the architectural rationale lives in
[ADR 0013](adr/0013-metadata-standardisation.md).

The mechanism has two graph-level components.

**`gather_reference_metadata`** runs after `research` and before
`draft_proposal`. It is deterministic. It calls three MCP cohort lookups
and writes a `reference_metadata` state field carrying three cohorts:

- **Cohort A** — sibling series in the same `indicator`
- **Cohort B** — series for the same `concept` across all geographies
- **Cohort C** — series for the same `provider` and same `concept`,
  joined through `series_sources`

Empty cohorts are recorded explicitly. When cohort A is empty, the state
flag `is_first_in_family` is set true; the governance reviewer and the
metadata skill both load extra content in response (`Seed exemplars`
inside the skill; first-in-family scrutiny in the reviewer).

**`classify_extraction_mode`** runs in parallel with
`gather_reference_metadata`. It is also deterministic. It calls
`list_selector_types` and `get_selector_schema`, compares the provider
shape from `research`, and writes the `extraction_mode` state field
(`config_only` or `custom_python`). The conditional edge into
`draft_script` reads this field; the drafter no longer needs to populate
it inside its generated proposal.

The drafter writes new prose anchored on cohort A → B → C in that
priority order. The drafter may emit harmonisation items proposing
updates to existing prose, but only under the four closed triggers in
the skill, and the default is to emit nothing.

For prose-adjacent fields that the agent cannot mutate directly
(`concept.name`, `indicators.name`, all `*.code` values), the
drafter emits items with `action = suggest_human_apply`. The
executor leaves these items as `pending_human_apply` rows; the
operator applies them via SQLAdmin and flips them to
`applied_by_operator`. This keeps every high-stakes suggestion
auditable through `change_proposals` rather than living in free-text
remarks.

Structural enum-backed fields are handled separately by the
enum-gap escalation flow (see below); they do not ride on
`suggest_human_apply`.

## Enum-gap escalation

When the drafter is about to populate a structural enum-backed
column (`series.frequency`, `series.seasonal_adjustment`,
`series.measure`, `series.measure_horizon`, `series.unit_kind`,
`series.unit_scale`, `series.price_basis`, `series.reference_kind`,
`series.temporal_stock_flow`) and discovers that the candidate
series' real-world methodology cannot be faithfully represented by
any existing value of the relevant enum, the drafter must not
coerce silently. It emits an `EnumGapProposal` on its
`enum_gap_proposals` output and returns without a draft.

The discipline for emitting a gap (the three conditions —
no-existing-value-fits, catalog-impact, provider-evidence — plus the
anti-pattern list and the drop-on-missing-evidence rule) lives in
[skill-enum-gap-escalation](skills/skill-enum-gap-escalation.md).
The architectural rationale lives in
[ADR 0014](adr/0014-enum-gap-escalation.md).

A non-empty `enum_gap_proposals` field routes the graph to a new
human-interrupt node `enum_gap_wait`, distinct from Gate 1. The
node renders the proposed enum value(s), the rationale, the cited
provider evidence, and an inline operator-instruction block: a
fully-rendered Python enum edit, a copy-pasteable Alembic migration
template populated from the ADR 0005 idiom, and the exact resume
command. The picker is structured: `Apply later (pause)`,
`Decline and coerce`, `Abort`.

On `Apply later`, the session checkpoints and the CLI exits cleanly.
The operator does the code+migration work in a separate terminal,
applies the migration as `macrodb_owner` against the session's
target database (`macrodb_staging` by default), and resumes with
`macrodb onboard --resume <session-id>`.

On resume, `enum_gap_wait` walks each pending proposal and verifies
the proposed value is present in **both** the Python enum class
(via fresh import) and the DB CHECK constraint (via a new MCP tool
`list_enum_values(table, column)` that reads `pg_constraint`).
Both must pass before the gap is recorded as `applied`. If a value
was added under a different name than proposed (e.g. operator added
`both_sa` instead of the proposed `BSA`), a reconciliation prompt
asks whether the renamed value satisfies the proposal; on
confirmation the resolution is recorded as `applied_renamed`.

On `Decline and coerce`, the operator types a rationale and names
the existing value to use; the drafter re-runs with `coerce_hints`
and `coerce_rationales` state fields populated and produces a
proposal that uses the operator's chosen value. No automatic
prose note is added to the affected series; the audit row
preserves the original judgment.

On `Abort`, the session terminates via the existing `abort` node
with reason `enum_gap_declined`.

Each `EnumGapProposal` produces its own `change_proposals` row,
created at the point the operator picks `Apply later (pause)`. The
row is linked to the session via `source_agent_session_id` but its
lifecycle is **independent** of the session's main onboarding
proposal: the enum widening, once committed, is real code in the
repo regardless of whether the session ultimately succeeds, and
the audit row reflects that.

Schema additions ADR 0014 introduces on the governance enums:

- `Action`: new value `suggest_enum_addition`
- `TargetType`: new value `ENUM_VALUE`
- `ValidationStatus`: new value `declined_by_operator`

These are CHECK-constraint widenings under ADR 0005, applied via
standard Alembic migrations.

Structural gaps that are not enum-value gaps — a methodological
distinction macrodb has not modelled at all, requiring a new
column — are out of scope. The drafter aborts with reason
`schema_deficiency` and the gap is addressed in a separate
operator-led design pass.

## Credential-gap escalation

When the `research` role attempts a provider probe and the
three-layer pre-check fails (existing `providers.credentials_ref`
lookup → `os.environ.get` → real probe), the agent must not coerce
silently. It emits a `CredentialGapProposal` on its
`credential_gap_proposals` output and blocks. The graph routes to a
new human-interrupt node `credential_gap_wait`, distinct from both
Gate 1 and `enum_gap_wait`.

The discipline for emitting a gap (the three conditions —
provider-materially-requires-key, pre-check-confirmed-missing,
direct-doc-evidence — plus the anti-pattern list and the
drop-on-missing-evidence rule) lives in
[skill-credential-gap](skills/skill-credential-gap.md). The
architectural rationale lives in
[ADR 0016](adr/0016-credential-gap-escalation.md).

`credential_gap_wait` renders, for each gap: the provider identity,
the proposed env var name, the proposed auth scheme, the inferred
rate limit (operator can confirm or edit), the cited evidence URL
and snippet, the rationale, and inline operator instructions
(where to obtain the key, how to set the env var, and the exact
resume command). The picker is **2-option**: `Apply later (pause)`
and `Abort`. There is no "Decline and override" option (asymmetric
with `enum_gap_wait`'s 3-option picker) because the probe is the
ground truth: the operator can leave the env var unset, pick
`Apply later`, and the resume probe will decide whether a key is
genuinely required.

On `Apply later`, the session checkpoints and the CLI exits
cleanly. The operator obtains the key out of band, sets the env
var in their shell or secret store, and resumes with
`macrodb onboard --resume <session-id>`. On resume,
`credential_gap_wait` re-runs the probe with the env var. Success
records `outcome = provisioned`; a renamed env var (operator pasted
a different name in chat) records `outcome = provisioned_renamed`;
persistent 401/403 re-renders the picker for rotation or abort.

On `Abort`, the operator types a rationale (required); the session
terminates via the existing `abort` node with reason
`credential_unavailable`.

Provider-row write timing is **asymmetric with enum-gap**:
credential-gap-apply does NOT write to `providers`. The agent reads
the env var directly from `os.environ` during research and
`validate_script`. At Gate 1 `apply_catalog`, the `providers` row
is INSERTED (new provider) or UPDATED (existing provider) with
`credentials_ref`, `auth_scheme`, `rate_limit_config` populated
from the audit row. This honours the gate invariant that nothing
is committed before Gate 1 approves.

Each `CredentialGapProposal` produces its own `change_proposals`
row, linked to the session via `source_agent_session_id` but with
an independent lifecycle. A provisioned credential is real
operator-machine state regardless of whether the session ultimately
succeeds; the audit row reflects that.

Schema additions ADR 0016 introduces:

- `Action`: new value `suggest_credential_provisioning`
- `TargetType`: new value `CREDENTIAL_REF`
- new column `providers.auth_scheme` (column-backed `AuthScheme`
  enum with values `BEARER_HEADER`, `QUERY_PARAM`, `HEADER_CUSTOM`,
  `BASIC_AUTH`, `NONE`)
- new column `providers.rate_limit_config` (JSONB)
- `providers.credentials_ref` reused if present or added if not

OAuth flows, IP allowlists, and client-certificate auth are out of
scope for v1. If a future provider needs an auth scheme not in the
`AuthScheme` enum, the gap composes with enum-gap: an
`EnumGapProposal` on `AuthScheme` fires first, the operator widens
the enum, and only then can the credential-gap proceed.

The agent **never** records the credential value itself. The
schema, audit rows, state fields, and logs contain only the env
var name, auth scheme, and rate-limit metadata. The value is
read from `os.environ` at probe time and passed directly to the
HTTP client; both research probes and the ingestion runtime use
the same path.

The credential-gap pattern and the enum-gap pattern share a
documented shape ("escalation gap") — same picker semantics, same
pause/resume mechanics, same audit-row-per-gap discipline — but
distinct nodes, state fields, and audit values. Shared Python
implementation lives in `agent/escalation/`. See ADR 0014 and
ADR 0016 for the per-kind rationale.

## Skill loading

Domain knowledge lives in narrow, single-purpose skills under `docs/skills/`.
Skills are lazy-loaded into LLM context per call, driven by state-side
triggers, not statically per role.

Each node declares a small `skill_triggers` map of `(state_predicate,
skill_id)` pairs. Before each LLM call, the node walks its triggers, evaluates
each predicate against current graph state, and assembles its prompt as the
role's base system prompt plus the selected skill bodies. A node working on a
flat single-series onboarding may load zero skills; a node working on a
candidate hierarchy enrichment loads the hierarchy and concept-boundary
skills.

This is the operational form of the broader principle in
`docs/architecture.md`: helpers and skills must stay narrow and
context-efficient. No node should carry domain context it does not currently
need.

A skill is domain knowledge, not procedural instructions. A skill explains
*what makes a hierarchy edge same-concept*; it does not say "first do X, then
do Y." Procedural orchestration is the graph's job, not the skill's.

## Script lifecycle

Most new feeds need no Python: an existing `selector_type` covers the provider
and the agent produces only a `selector_config` plus catalog rows. Custom
Python is required only when the provider's request encoding, response shape,
or extraction semantics fall outside the existing selector registry.

When custom Python is required:

1. The script drafter writes a proposed selector extension to
   `agent_workspace/proposed_selectors/<session_id>/` at the repo root. This
   directory is gitignored. The main codebase is never touched directly by
   the agent.
2. The validator runs the sandboxed selector against a probe payload and
   reports parsed observations.
3. The selector reviewer reviews the diff against
   `skill-ingestion-selector-conventions` and surfaces findings.
4. Gate 1 approves catalog rows and the proposed selector as one bundle.
5. The executor's `apply_catalog` node promotes the sandboxed selector into
   `src/macro_foundry/ingestion/runtime/selectors/<name>.py`, registers it,
   and runs the relevant tests as part of the promotion step.

Hard invariants:

- the agent must never run `git commit` or `git push`
- the agent must never modify files under `src/` outside the explicit
  promotion step
- the operator is the only commit author; promotion of a selector into the
  runtime is an explicit operator-approved action, not a side effect

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

- run first in the staging database (see `docs/environments.md`); never in
  `macrodb_test`, which is pytest-only
- the trigger and monitor steps are separate graph nodes so the monitor is
  resumable across CLI session pauses
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

`staging -> prod` should be handled later as a separate outer deployment
workflow or promotion graph.

This document stops at:

- approved catalog/feed setup in `staging`
- a monitored initial ingestion run in `staging`
- human review of the staging-run outcome

## Output artifact

This workflow should end by producing a durable test-approved onboarding
package.

That package is the handoff boundary between:

- this onboarding graph
- a later outer deployment or promotion workflow

Minimum contents:

- approved proposal summary
- the canonical rows created or updated in `staging`
- reviewer findings, flags, and final status (governance — including
  any conditional selector-code findings — and data correctness)
- first-run ingestion summary
- warnings or tolerated issues recorded during the initial backfill
- explicit status that the package is `test-approved`
- back-references to the originating LangGraph `thread_id` and the
  `change_proposals.id` row that records the approved change set

## LangGraph fit

This workflow is a state machine, not a chain of events. Conditional edges
between nodes are driven by the state dict (proposal confidence, ambiguity
flags, dangerous-correction flag, review cycle count, gate status, first-run
outcome), not by fixed arrows.

Node inventory (v1):

- `research` — folds intake; reads provider docs, runs web search and probe
  fetches, populates `source_summary` and `existing_catalog_hits`
- `gather_reference_metadata` — deterministic; calls three MCP cohort
  lookups (siblings, cross-geography same-concept, same-provider
  same-concept); writes `reference_metadata` and `is_first_in_family` to
  state; records empty cohorts explicitly
- `classify_extraction_mode` — deterministic; calls `list_selector_types`
  and `get_selector_schema`; writes `extraction_mode` (`config_only` or
  `custom_python`) to state; runs in parallel with
  `gather_reference_metadata`
- `draft_proposal` — produces catalog and feed-member draft; reads
  `reference_metadata` to anchor prose; may emit harmonisation
  side-output for existing prose under the four closed triggers; emits
  propose-only prose-adjacent fields with
  `action = suggest_human_apply`; may emit
  `enum_gap_proposals` and return without a draft when a structural
  enum-backed field cannot be populated faithfully
- `enum_gap_wait` — human-interrupt; reached only when
  `enum_gap_proposals` is non-empty. Renders proposed enum value(s),
  rationale, cited evidence, and inline operator instructions
  (Python diff + Alembic migration template + resume command).
  Picker: `Apply later (pause)` | `Decline and coerce` | `Abort`.
  On resume, verifies each gap via Python introspection + DB CHECK
  constraint check (via `list_enum_values` MCP tool); handles
  reconciliation of renamed values; records resolutions in
  `enum_gap_resolutions` and one `change_proposals` row per gap.
  See [ADR 0014](adr/0014-enum-gap-escalation.md).
- `draft_script` — only when `extraction_mode == "custom_python"`, writes to
  sandbox
- `validate_script` — executes the selector against a probe payload
- `credential_gap_wait` — human-interrupt; reached only when
  `credential_gap_proposals` is non-empty (research's pre-check
  failed). Renders provider identity, proposed env var name and
  auth scheme, inferred rate limit, cited evidence, and inline
  operator instructions. Picker: `Apply later (pause)` | `Abort`.
  On resume, re-runs the probe with `os.environ` to verify;
  records resolutions in `credential_gap_resolutions` and one
  `change_proposals` row per gap. Provider-row writes are deferred
  to Gate 1 `apply_catalog`. See
  [ADR 0016](adr/0016-credential-gap-escalation.md).
- `governance_review`, `data_correctness_review` — parallel
  reviewers. Selector code review is folded into governance as a
  conditional skill load when `extraction_mode == custom_python`;
  it is not a separate role. See
  [ADR 0015](adr/0015-reviewer-role-consolidation.md).
- `gate_1_wait` — interrupt, awaits structured approval
- `approval_parse` — classifies user reply via the structured picker; extracts
  edit instructions inside the `Request changes` branch
- `apply_small_edit` — runs uniqueness pre-check on touched UNIQUE columns,
  branches on collision
- `apply_catalog` — transactional catalog write and selector promotion
- `trigger_first_run` — fires the new feed
- `monitor_first_run` — resumable polling to terminal status
- `test_review` — synthesizes the first-run outcome
- `emit_package` — writes the durable test-approved onboarding package
- `dangerous_correction_plan` — impact analysis and repair drafting
- `abort` — terminal node with reason

Refinements to this inventory are expected as the implementation matures and
should be captured as ADR-level updates when they affect role boundaries or
gate semantics.

## Implementation note

The implementation is a LangGraph state machine driven by a chat-style Typer
CLI. The CLI runs as a foreground process and persists graph state via
LangGraph's `PostgresSaver` against a `langgraph` schema in the same Postgres
database that hosts `macrodb`. There is no daemon; pause/resume is handled by
the checkpointer and an `--resume <session-id>` flag.

Agents reach macrodb only through a custom `macrodb-mcp` server with a
narrow, semantic tool surface (`lookup_concept`, `lookup_family`,
`find_sibling_series`, `propose_create_series`, `apply_approved_proposal`,
`list_selector_types`, `get_selector_schema`, `validate_selector_config`,
`trigger_feed_execution`, etc.). Read-only and write-enabled MCP instances are
served from the same codebase but bind different tool subsets, so the
read-only reviewer role cannot reach a write tool by mistake. Generic Postgres
MCPs that expose raw SQL are explicitly rejected for this purpose.

Skills are Markdown documents under `docs/skills/`, lazy-loaded per LLM call
based on state-side triggers. They are domain knowledge, not procedural
instructions.

Per-role LLM configuration lives in `src/macro_foundry/agent/roles.py` as
typed `RoleConfig` objects. Within-role tiering (e.g., a quick scan call vs. a
deep reasoning call inside the same role) is expressed via the role's
`models_by_task` map and a `task_hint` at the call site.

The likely next workflow layer after this document is a separate deployment or
promotion graph for moving a test-approved onboarding package from `staging`
into `prod`.
