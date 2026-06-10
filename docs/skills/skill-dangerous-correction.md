---
status: accepted
---
# skill-dangerous-correction

**Status:** accepted

## Scope

When the workflow should branch into the Gate 2 dangerous-correction path
versus continuing with ordinary onboarding. Covers the publication-boundary
test, the three triggers, and the shape of the repair plan that a
dangerous-correction proposal must carry.

This skill does not cover ambiguity in *not-yet-published* identity
decisions (see [skill-ambiguity-handling](skill-ambiguity-handling.md)).

## Publication-boundary test

A series has crossed the publication boundary once *any* of the following
are true:

- `observations` rows have been written against the series
- `ingestion_run_logs` records exist for feeds that target the series
- the series appears in `series_hierarchy_edges` as a parent or child
- the series is referenced by a published `change_proposal` with
  `status = APPLIED`

If none of these are true, the series is still in proposal space and a
simple code correction can be made without triggering Gate 2.

## Trigger conditions

Three paths lead to the dangerous-correction branch. All three must be
treated with the same level of care.

**1. Researcher-detected identity problem**
The research node determines that a series already in the catalog has
the wrong canonical code — wrong variant scope, missing SA/measure
tokens, or provider ticker leaked into the code. The researcher should
not silently propose a new series with the correct code and leave the
old one behind. Instead, surface the identity problem explicitly in
`ambiguity_flags` and set `gate_2_escalation = True` in state.

**2. Reviewer diagnosis**
Either the governance reviewer or the data-correctness reviewer
determines that the existing catalog identity is materially wrong
(not just a prose issue). The reviewer should record this as a
`bounce_to_drafter = True` finding with a specific instruction to
flag the identity problem and trigger the dangerous-correction path
in the next draft cycle.

**3. Uniqueness collision during small edit**
The operator requests a textual edit at Gate 1 (e.g., "rename the
series code"), uniqueness pre-check detects that the proposed code
already belongs to a published series, and the operator selects
**Treat existing as wrong** from the three-way collision picker.
This sets `gate_2_escalation = True` and routes to
`dangerous_correction_plan`.

## The dangerous_correction_plan node

The planner LLM must produce a `DangerousCorrectionPlan` with all of
the following fields:

| Field | What to include |
|---|---|
| `collision_column` | Which UNIQUE column is in conflict (usually `series.code`) |
| `existing_code` | The current (wrong) canonical code in the catalog |
| `proposed_code` | The correct code being proposed |
| `affected_source_mappings` | UUIDs of `series_sources` rows that point at this series |
| `affected_feeds` | UUIDs of `ingestion_feeds` routed through the wrong series |
| `affected_observations_count` | Approximate number of observation rows that carry the wrong identity |
| `affected_derivations` | Codes of derived series computed from this series (e.g., YoY variants) |
| `repair_strategy` | One of: `rename_in_place`, `supersede_and_replace`, `route_future_only` |
| `repair_rationale` | One or two sentences explaining the chosen strategy |

**Do not omit any affected-rows category.** An incomplete impact
analysis is worse than no analysis — it makes Gate 2 approval
misleading.

## Repair strategies

**`rename_in_place`** — Rename `series.code` and all downstream
references atomically. Source mappings, feeds, observations, hierarchy
edges, and derivation inputs all remain; only the code changes. Use
this when:
- the series has crossed the publication boundary but the number of
  affected rows is small and well-understood
- there is no risk of confusion with an existing series that already
  has the proposed code

**`supersede_and_replace`** — Create a new canonical series with the
correct code and mark the old series as superseded. Observations stay
on the old series (preserving vintage history); new ingestion is routed
to the new series. Use this when:
- the affected observation history is large or critical to preserve
  under the original identity
- the wrong series identity might have been shared with external
  consumers

**`route_future_only`** — Leave historical observations and feeds
under the wrong series code; create a new series for future ingestion
only. Use this sparingly — it creates a permanent identity split that
is harder to merge later. The default bias should be
`supersede_and_replace` unless there is a strong reason to avoid it.

## Gate 2 approval semantics

Gate 2 uses the same three-option structural picker as Gate 1:
`Approve`, `Reject`, `Request changes`.

- **Approve** → `dangerous_correction_executor` applies only the
  approved repair plan. No routine catalog writes are permitted in
  this executor branch.
- **Reject** → Graph ends. The existing wrong series remains; the
  operator must decide offline what to do.
- **Request changes** → The approval LLM parses the operator's
  free-text instructions into re-plan directives, and the graph loops
  back to `dangerous_correction_plan`.

## Executor scope constraint

The `dangerous_correction_executor` node is **scoped to the approved
repair plan only**. It must not:

- create new concepts, families, or series beyond what the repair plan
  specifies
- write new observations
- trigger new ingestion runs
- apply any `suggest_human_apply` items

If the scope needs to expand beyond what the plan describes, the
operator must submit a new onboarding session or a fresh Gate 2 pass.

## Anti-patterns

- **Silent code correction**: applying `series.code` rename without a
  Gate 2 approval is forbidden once the series has crossed the
  publication boundary.
- **Auto-selecting the repair strategy**: the planner should recommend
  a strategy with clear rationale but the operator approves or rejects
  it at Gate 2.
- **Omitting derivation impact**: a YoY series computed from a
  wrongly-coded base series must appear in `affected_derivations`.
- **Reusing apply_catalog for the repair**: the dangerous-correction
  executor must not call `apply_catalog`'s routine write path; it has
  its own scope-limited writer.

## When triggered

- node is `dangerous_correction_plan`, `gate_2_wait`, or
  `dangerous_correction_executor`
- `state.gate_2_escalation` is `True`
- a uniqueness collision was surfaced and the operator chose
  `challenge_existing`
- a reviewer's `bounce_to_drafter` finding contains an explicit
  identity-correction instruction

## Body

Use the publication-boundary test to decide whether Gate 2 is required.
If the series has not crossed the publication boundary, a simple
`apply_small_edit` correction is sufficient — do not escalate to Gate 2.

If Gate 2 is required, produce a complete `DangerousCorrectionPlan`
covering all affected rows. Choose the repair strategy from the three
options (`rename_in_place`, `supersede_and_replace`, `route_future_only`)
using the criteria above, and write a clear rationale. The operator must
be able to approve or reject the plan without needing to re-derive the
impact from scratch.

At Gate 2, wait for an explicit `Approve` signal before executing any
repair. Execution is scoped to the approved plan only — no routine
catalog writes, no new observations, no new ingestion triggers.
