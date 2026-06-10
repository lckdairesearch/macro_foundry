# ADR 0014 — Enum-gap escalation in the gated onboarding workflow

**Status:** Accepted

**Date:** 2026-06-10

## Context

ADR 0011 ratifies the gated onboarding graph, and ADR 0013 closes the
metadata-standardisation thread by defining how the proposal drafter
treats prose fields. ADR 0013's per-field mutation matrix classifies
structural enum-backed fields (`series.frequency`,
`series.seasonal_adjustment`, `series.measure`, `series.unit_kind`, etc.)
as propose-only and deferred their escalation mechanism to a separate
ADR. This ADR is that follow-on.

The problem ADR 0014 resolves is what happens when the onboarding agent
encounters a candidate series whose real-world methodology cannot be
faithfully represented by the existing values of one of those enums.
For example, a provider publishes a series labelled as trend-cycle
adjusted, which is distinct from `SA`, `SAAR`, and `NSA`; or a provider
publishes a 10-day "dekad" frequency that does not appear in
`Frequency`.

Two paths exist today and both are bad:

- **Coerce.** Pick the closest existing enum value and silently lose
  the methodological distinction. Catalogues this way accumulate hidden
  classification errors that downstream consumers cannot detect.
- **Block.** Abort the session entirely. Wastes the research, cohort
  retrieval, and drafting work, and creates pressure on future sessions
  to coerce rather than escalate.

The operator's framing is unambiguous: **the agent must never force**.
Coerce-without-disclosure is the failure mode to design against.

ADR 0005 fixes the enum-evolution mechanism. Enums in macrodb are
Python `str, Enum` classes plus `SAEnum(..., native_enum=False,
name="ck_<table>_<col>")`. Widening an enum is a two-step change:
edit the Python enum class and write an Alembic migration that
re-issues the named CHECK constraint with the new value list. The
migration template is fixed.

ADR 0006 fixes the boundary between roles. Migrations run as
`macrodb_owner`; the agent's read-write MCP server has `macrodb_app`
only. The agent cannot widen an enum on its own. The work is
unavoidably an operator action.

ADR 0013's `suggest_human_apply` action covers the precedent of
"agent proposes, human applies", but it was deliberately scoped to
catalog-row mutations the operator performs in SQLAdmin. Enum widening
is structurally different: the operator's action is a code commit
plus an Alembic migration revision, and verification of "did the
operator actually finish?" is mechanical (Python introspection + DB
CHECK constraint check) rather than a manual SQLAdmin button click.
Reusing `suggest_human_apply` would dilute its meaning.

The handoff thread distinguished "enum-value gaps" from "column gaps"
(macrodb has not modelled the distinction at all). The two have
materially different design surfaces; this ADR covers only enum-value
gaps. Column gaps abort with a recorded reason and are deferred to
their own ADR-shaped discussion.

## Decision

### Scope

ADR 0014 governs **enum-value gaps only** on a closed allowlist of
series-methodology enums. The allowlist is the series-methodology
subset of [src/macro_foundry/enums/series.py](../../src/macro_foundry/enums/series.py)
minus `OriginType`:

`Frequency`, `SeasonalAdjustment`, `Measure`, `MeasureHorizon`,
`UnitKind`, `UnitScale`, `PriceBasis`, `ReferenceKind`,
`TemporalStockFlow`.

`OriginType` and every governance, provider, derivation, run, or
geography enum are excluded. If the agent ever feels one of those
needs a new value, that is an architecture conversation, not an
onboarding escalation.

Any structural gap that is *not* an enum-value gap (a methodological
axis macrodb has not modelled at all, requiring a new column) is out
of scope. The drafter records the case in chat, the session is
aborted via the existing `abort` node with reason
`schema_deficiency`, and the gap is addressed in a separate operator-led
design pass.

### Detection: inside `draft_proposal`, no new node

The drafter is the entity that populates enum-typed columns on the
candidate series. A gap is discovered *during* drafting, by definition.
The metadata session's principle that routing should not depend on
parsing LLM output is preserved by adding **structured output fields**
to the drafter, not by adding a sibling deterministic node.

The drafter's output gains two fields:

- `enum_gap_proposals: list[EnumGapProposal]` — empty in the common
  case; populated when the drafter cannot pick a value for one or more
  allowlisted enums
- `draft: DraftProposal | None` — populated only when
  `enum_gap_proposals` is empty

A conditional edge after `draft_proposal` reads
`enum_gap_proposals`. If non-empty the graph routes to
`enum_gap_wait`. If empty the graph proceeds to the parallel reviewers
as before. The router reads a typed state field, not generative text.

The drafter detects every gap in one pass against the full allowlist;
it does not stop at the first one.

### Human interrupt: new node `enum_gap_wait`

`enum_gap_wait` is a human-interrupt node distinct from `gate_1_wait`.
Gate 1 approves a drafted bundle; here there is no drafted bundle to
approve. Folding the interrupt into Gate 1 would corrupt Gate 1's
semantic the same way ADR 0013 refused to corrupt Gate 2 with prose.

The node renders, for each gap:

- the proposed value and symbolic name
- the rationale
- the cited provider evidence
- inline operator instructions: a fully-rendered Python enum edit
  diff, a copy-pasteable Alembic migration template populated from
  the ADR 0005 idiom (already a fixed 8-line shape), and the exact
  resume command

It then offers a structured picker:

- **Apply later (pause)** — session checkpoints; CLI exits cleanly. The
  operator does the code+migration work, applies as `macrodb_owner`
  against the session's target database, and resumes with
  `macrodb onboard --resume <session-id>`.
- **Decline and coerce** — operator types a free-text rationale plus
  the existing enum value to use; the agent records the resolution and
  re-runs the drafter with a `coerce_hints` state field telling it the
  forced value and explanation.
- **Abort** — session terminates via the existing `abort` node with
  reason `enum_gap_declined`.

The node does not generate Alembic migration files into a sandbox.
The migration is short and stable enough that inline templating beats
a sandbox + filename-convention path.

### Pause / resume verification

Two state fields drive the lifecycle:

- `enum_gap_proposals: list[EnumGapProposal]` (set by drafter)
- `enum_gap_resolutions: list[EnumGapResolution]` (set in
  `enum_gap_wait`)

`EnumGapProposal` carries `enum_path`, `proposed_value`,
`proposed_name`, `rationale`, `cited_evidence`, `existing_values_considered`,
`catalog_impact`. `EnumGapResolution` carries `outcome ∈ {applied,
applied_renamed, declined_coerce, aborted}`, `applied_value`,
`operator_rationale`, `resolved_at`.

On resume, `enum_gap_wait` walks each pending proposal. For each one:

1. **Python check.** Re-import the enum class (the `--resume` process
   is a new process, so a fresh import sees the operator's edits).
   Confirm `proposed_value in {e.value for e in EnumClass}`.
2. **DB check.** Call a new MCP tool `list_enum_values(table, column)`
   that reads the named CHECK constraint expression from
   `pg_constraint`, parses the `IN (...)` literal, and returns the
   value list. Confirm the proposed value is in it.

Both pass → record `outcome = applied`. The drafter resumes with the
new vocabulary visible.

If a **different value appeared** in the enum since pause, surface a
reconciliation prompt: "you added `both_sa`, which was not there at
pause time; did you mean it as the value for the proposed `BSA`?"
A yes resolution records `outcome = applied_renamed` and
`applied_value = both_sa`. A no resolution keeps waiting on the
originally proposed value.

If the proposed value is still absent, re-render the picker. The
operator may apply later again, decline this specific gap and coerce,
or abort.

All gaps must be resolved (applied / applied_renamed /
declined_coerce) before the drafter resumes. Partial resolution
across multiple resumes is fine.

### Audit trail in `change_proposals`

Three schema deltas on the governance enums:

- `Action`: new value `suggest_enum_addition`
- `TargetType`: new value `ENUM_VALUE`
- `ValidationStatus`: new value `declined_by_operator`

Each enum-gap proposal produces **its own** `change_proposals` row
created at the point the operator picks `Apply later (pause)`. The
row is linked to the session via the existing
`source_agent_session_id` FK introduced by ADR 0011 but its lifecycle
is independent of the session's main onboarding proposal.

This separation matters: if the operator widens `SeasonalAdjustment`
to add `BSA` and then aborts the session for unrelated reasons, the
enum addition is still real code in the repo. It must show as
`applied` regardless of the session's outcome. The audit semantics
attach to the operator action, not to the session.

| Operator action | `change_proposals.status` | Item `validation_status` |
|---|---|---|
| Adds + migrates + resume verifies | `applied` | `applied_by_operator` |
| Renames; reconciled on resume | `applied` | `applied_by_operator`; `proposed_data` records `applied_value` differing from `proposed_value` |
| Declines, coerces | `rejected` | `declined_by_operator`; `proposed_data` records `coerced_to` and `operator_rationale` |
| Aborts session entirely | `rejected` | `declined_by_operator` |

No new `ProposalStatus` values are needed. No new MCP tool is needed
besides `list_enum_values`.

### Anti-laziness discipline

The agent may emit an `EnumGapProposal` only when all three of these
hold, and each proposal must carry structured evidence for each
claim:

1. **No existing value fits.** The drafter has walked the full enum
   and articulated, per existing value, why it does not represent the
   series faithfully.
2. **The distinction matters for catalog identity.** The gap captures
   a methodological distinction downstream consumers would care about
   (queries against the structural column would route incorrectly).
   Distinctions absorbable into prose without losing query semantics
   stay in prose.
3. **The provider's documentation supports it.** The gap reflects
   something the provider explicitly publishes, not the drafter's
   inference.

`EnumGapProposal` schema:

- `enum_path` — fully-qualified Python path of the enum class
- `proposed_value` — literal string value
- `proposed_name` — symbolic identifier
- `existing_values_considered` — `dict[str, str]` mapping each existing
  value to a one-line dismissal
- `provider_evidence` — cited URL + snippet
- `catalog_impact` — one line on why the distinction matters for
  queries
- `rationale` — one line, ≤200 characters

Proposals with missing or empty evidence fields are **dropped before
the gap signal is set on state**. The drafter that emits an
evidenceless gap silently demotes to "pick the closest value and flag
in prose." This makes "lazy gap" structurally hard.

The skill `skill-enum-gap-escalation` carries an explicit anti-pattern
list of things that never justify a gap (cosmetic complaints about
existing value names, synonym differences, free-text provider
classifications, minority distinctions outside standard macro
practice, and drafter uncertainty about which existing value applies).

### Coerce-with-explanation: no automatic prose pollution

When the operator picks `Decline and coerce`, the drafter on re-run
reads `coerce_hints` and uses the operator-chosen value. The
operator's rationale lives in the gap's `change_proposals` row, not
in the series' `name` or `description` prose. The coercion was a
curatorial decision by the operator; the catalog now reflects it.
Future queries against the coerced value correctly include this
series; that is the operator's intent. The metadata-standardisation
skill's rule against runtime-implementation detail in prose applies
uniformly.

If the operator wants a prose note explaining the coercion for this
specific series, they add it themselves at Gate 1 via the
`Request changes` path.

## Consequences

**Positive.**

- The "agent never forces" property becomes a structural guarantee.
  Coercion requires an explicit operator picker action with a recorded
  rationale; silent coercion is not on the drafter's path.
- The pause/resume mechanism preserves the research, cohort retrieval,
  and partial drafting work across the operator's code+migration cycle.
  Aborting a several-step session to widen an enum is no longer the
  only option.
- Multi-gap sessions are handled in one pause, not N. The operator
  can bundle commits or split them at their discretion.
- The audit trail makes every enum addition queryable through
  `change_proposals` with `target_type = ENUM_VALUE`. "Show me every
  enum value the agent ever proposed" becomes a single query, as does
  "show me every declined-and-coerced gap with the operator's
  rationale."
- The verification mechanism (Python + DB CHECK constraint) closes the
  hole where the operator could edit Python but forget the migration
  (or vice versa). The resume cannot proceed until both are consistent.
- The reconciliation prompt for renamed values turns a common UX
  failure (operator added `both_sa` instead of the proposed `BSA`)
  into a one-click reconciliation instead of a forced abort or a wrong
  re-prompt.
- The discipline section (three conditions + evidence + anti-pattern
  list) protects against the opposite failure mode of lazy gaps that
  interrupt the operator for cosmetic reasons.

**Negative.**

- One new human-interrupt node (`enum_gap_wait`), one new MCP tool
  (`list_enum_values`), and three new governance-enum values
  (`Action.suggest_enum_addition`, `TargetType.ENUM_VALUE`,
  `ValidationStatus.declined_by_operator`).
- The drafter's output schema gains an `enum_gap_proposals` field and
  a structured branch on emptiness. The drafter prompt must be
  explicit about the three conditions and the anti-pattern list.
  Skill `skill-enum-gap-escalation` carries this; failure to follow
  it reduces to noisy interrupts, not silent corruption.
- The wait node renders operator instructions inline, including a
  populated Alembic migration template. If the migration idiom from
  ADR 0005 ever changes, the wait node's template needs to follow.
  Acceptable because the idiom is stable and the template is short.
- Column-gap escalation is out of scope. If the agent encounters a
  true column gap, the session aborts and the operator addresses it
  via a separate design pass. Not all structural shortcomings are
  covered by this ADR.

## Alternatives considered

- **Drafter detects but does not emit gaps; coerces with prose note
  in every case.** Rejected. This is exactly the "agent forces" mode
  the operator framed as the failure to design against. The audit
  trail would also be impossible to query — gaps would be hidden in
  free-text remarks.
- **A new sibling node `detect_enum_gap` runs deterministically before
  `draft_proposal`.** Rejected after grilling. Enum-gap detection is
  not deterministic — it requires LLM reasoning about whether existing
  values stretch to cover the provider's methodology — and the drafter
  must do the same classification anyway to populate enum columns.
  Pulling it out duplicates the work and adds node count without
  cleanly separating concerns. Keeping detection inside the drafter
  with a structured output field is simpler and preserves the
  "routing reads a state field, not generative text" principle.
- **Fold `enum_gap_wait` into `gate_1_wait`.** Rejected as a category
  error. Gate 1 approves a drafted bundle; at escalation the bundle
  does not exist. Reusing Gate 1's picker (`Approve` / `Reject` /
  `Request changes`) makes no sense for an enum widening. Same
  reasoning as ADR 0013's refusal to overload Gate 2 with prose.
- **Reuse `Action.suggest_human_apply`.** Rejected. ADR 0013 scoped
  `suggest_human_apply` to catalog-row mutations the operator
  performs in SQLAdmin. Enum widening is a code commit plus an
  Alembic migration revision; the verification is automatic on
  resume rather than a SQLAdmin button click. The lifecycle differs
  enough that conflating the two actions would erode the meaning of
  both.
- **One `change_proposals` row per session, with enum-gap items
  attached.** Rejected. The enum addition has identity independent of
  the session's outcome — once the operator commits the value, it is
  available to all future sessions. Attaching it to a specific
  session's main row would force the row's status to misrepresent the
  operator's action (e.g. showing `rejected` even though the value
  was applied).
- **Sequential detection (first gap pauses, drafter re-runs after
  apply, discovers next gap, pauses again).** Rejected. Worse UX,
  and the data structure already supports lists. Parallel detection
  in one pause is honest about the drafter's classification pass.
- **Item-level picker at the wait node ("apply gap 1, decline gap 2,
  apply gap 3").** Rejected. The combinatorial UI gets ugly fast and
  the resume walk already supports per-gap resolutions across multiple
  resumes. The all-or-nothing picker is simpler and equally
  expressive.
- **Hard-count threshold on how many gaps a session may surface.**
  Rejected. Magic numbers invite Goodhart effects on the drafter (it
  finds reasons to coerce one of N gaps to stay under threshold). The
  discipline section (three conditions + evidence + anti-pattern list)
  is the structural defence; the operator can decline-and-coerce any
  number of gaps at pause time.
- **Generate the Alembic migration file into a sandbox following the
  selector script-drafter pattern.** Rejected. The migration template
  from ADR 0005 is a fixed 8-line idiom. Code-generating eight lines
  into a sandbox does not justify a filename-convention path plus a
  promotion step. Inline template rendering at the wait node keeps the
  operator in the loop and is materially simpler.
- **Auto-append a coercion note to `series.description` whenever the
  operator coerces.** Rejected. Pollutes thousands of catalog
  descriptions with internal-process detail; sets a bad precedent
  for runtime-implementation detail leaking into human-facing prose.
  The audit row preserves the original judgment for anyone who wants
  the historical record. The metadata-standardisation skill's prose
  discipline applies.
- **Allow gaps against `OriginType` and governance enums.** Rejected.
  These are macrodb's own control vocabulary. A gap there is an
  architecture decision for the operator, not a mid-session
  escalation.
