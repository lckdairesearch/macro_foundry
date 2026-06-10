# ADR 0013 — Metadata standardisation in the gated onboarding workflow

**Status:** Accepted

**Date:** 2026-06-10

## Context

ADR 0011 ratifies the gated onboarding graph and the proposal drafter role,
and ADR 0012 ratifies the selector-registry ingestion runtime. Neither
addresses how the proposal drafter handles **prose fields**: `description`
on `concept`, `series_family`, and `series`; `name` on the same three;
and `variant` on `series_family_members`. These are the fields a human
reads when navigating the catalog, and they live next to identity fields
(codes) and structural fields (enums and methodology columns) without
sharing their lifecycle.

Three forces shape the problem.

- The catalog is expected to grow to many thousands of series across tens
  of providers. Without a discipline, related series will accumulate
  inconsistent voice, inconsistent qualifier ordering, and inconsistent
  factual completeness. The agent's prose output is the most visible
  artefact of its work; cosmetic drift compounds.
- Prose is **not identity**. CONTEXT.md's publication boundary makes
  identity corrections dangerous because other rows depend on identity;
  prose carries no such dependency. Treating prose as if it were identity
  would route routine updates through Gate 2 and dilute the meaning of
  Gate 2.
- Conversely, treating prose as freely-editable invites a different
  failure mode: every onboarding session proposes cosmetic edits to
  existing siblings, producing change-proposal churn that erodes operator
  trust in the agent.

A coherent design must balance these. It must also reason about
**path-dependence**: the first series in a family anchors the voice of
every sibling that follows, so the first-write moment is the highest
stakes.

A small number of prose-adjacent fields — `concept.name`,
`series_family.name`, all `*.code` values, and structural enum fields —
should never be mutated by the agent even after gate approval. The
existing graph has no mechanism for "the agent proposed this; the human
must apply it from the backend"; an agent that wants to suggest such a
change today has nowhere to put it except free-text remarks. That gap
makes high-stakes suggestions invisible to audit and easy to lose.

## Decision

Add four interlocking pieces to the gated onboarding workflow defined by
ADR 0011, all governing how prose fields are handled.

**1. Cohort retrieval as a new graph node `gather_reference_metadata`.**
Inserted between `research` and `draft_proposal`. Deterministic, with at
most a small extractive LLM call. Reads three cohorts via the macrodb MCP
server:

- **Cohort A** — sibling series in the same `series_family` (via the
  existing `find_sibling_series` tool)
- **Cohort B** — series for the same `concept` across all geographies
  (via a new MCP tool `list_series_for_concept`)
- **Cohort C** — series for the same `provider` and same `concept`,
  joined through `series_sources` (via a new MCP tool
  `list_provider_series_for_concept`)

Cohort C explicitly does not read from `IngestionFeed`; feeds remain
prose-free per ADR 0010 / 0012. The node writes a `reference_metadata`
field to graph state, recording empty cohorts explicitly so the drafter
and reviewers can see what anchors were and were not available.

**2. Extraction-mode classification as a new graph node
`classify_extraction_mode`.** Inserted as a parallel sibling to
`gather_reference_metadata`. Reads the selector registry via
`list_selector_types` and `get_selector_schema`, compares the provider
shape recorded in `research`, and writes the `extraction_mode` state
field (`config_only` or `custom_python`). This is not strictly about
metadata standardisation, but its extraction is a natural companion to
the gather-reference-metadata extraction because both lift a discrete
classification problem out of the larger drafter call, and they are both
prerequisites of `draft_proposal`. The conditional edge from
`draft_proposal` to `draft_script` now reads a state field set
deterministically upstream rather than parsing one out of the drafter's
generated proposal.

**3. Mutation matrix per prose field, with a new
`suggest_human_apply` proposal-item action.**

| Field | Agent can mutate after Gate 1 approval | Agent can only propose; human applies via SQLAdmin |
|---|---|---|
| `series.name`, `series.description`, `series_family.description`, `concept.description`, `series_family_members.variant` | ✅ | — |
| `concept.name`, `series_family.name` | — | ✅ |
| `*.code` | — | ✅ (and only via Gate 2 if changing an existing code) |
| Structural enum-backed fields | — | ✅ (may require enum-gap escalation, deferred to a separate ADR) |

For propose-only fields, the agent emits a `change_proposal_item` with
`action = suggest_human_apply`. The executor's `apply_catalog` node
**skips** these items; they live in `change_proposals` with
`validation_status = pending_human_apply` until an operator marks them
applied in SQLAdmin (flipping the status to `applied_by_operator` and
stamping `applied_at` plus `applied_by`). This keeps every suggestion
auditable and linkable to the originating session.

**4. Scenario-2 routing: harmonisation as Gate 1 companion items.**
When the drafter, while writing new prose, notices that an existing prose
field on a sibling or cohort entry is wrong or significantly drifted,
those updates are bundled into the same Gate 1 proposal as the new
series. The drafter emits them as a side-output of `draft_proposal`, not
as a separate node. The Gate 1 summary visibly separates "new series"
from "update existing series prose" and from "suggest for human action";
the structured Questionary picker covers the whole bundle (whole-proposal
approval, no item-level checkboxes; the `Request changes` path handles
selective rejection).

Gate 2 retains its meaning of **identity correction** and is not
overloaded with prose updates.

The drafter may propose an update to existing prose only when the
proposed item fires one of four closed triggers, codified in
`docs/skills/skill-metadata-standardisation.md`:

| Trigger | Bar |
|---|---|
| `factual_incompleteness` | Low — always propose when fired |
| `factual_error` | Low — always propose when fired |
| `family_outlier` | High — requires showing a clear consensus among siblings; single-sibling disagreement is not consensus |
| `house_voice_outlier` | Highest — requires showing a clear consensus across cohort B; cosmetic differences excluded |

The skill carries an explicit anti-pattern list (synonym swaps,
capitalisation normalisation, qualifier reordering, aesthetic
preferences, retroactive application of current hard rules to grandfathered
prose) and a per-item evidence structure (trigger code, cited schema
field or cited cohort members + shared pattern + this row's divergence,
proposed diff). Items with missing evidence are dropped before Gate 1.
The governance reviewer judges whether the cited chorus is loud enough;
there is no mechanical threshold.

**Path-dependence: first-in-family scrutiny.** When
`reference_metadata.cohort_A_empty == true`, the state field
`is_first_in_family = true` is set, and the governance reviewer loads
extra scrutiny content. The metadata-standardisation skill conditionally
loads a `Seed exemplars` sub-section containing operator-reviewed
canonical example prose entries so the drafter has anchor language even
when no siblings exist.

## Consequences

**Positive.**

- Catalog prose stays consistent across related series without forcing
  every onboarding session to litigate house voice from scratch. Cohort
  retrieval makes the anchor language available; the discipline says
  match it.
- Cosmetic drift is structurally suppressed. The four-trigger asymmetry
  (factual cheap, style expensive) plus the anti-pattern list plus the
  drop-on-missing-evidence rule combine to make "change for changes'
  sake" hard to commit by accident.
- Gate 2 stays semantically about identity. Routine prose updates never
  reach it.
- High-stakes propose-only suggestions (concept name, family name,
  codes) become auditable through `change_proposals` rather than living
  in free-text remarks. The operator can later query "what did the agent
  propose, what got applied, what is still pending?".
- The conditional edge into `draft_script` now reads a deterministic
  upstream state field, eliminating one place where the router would
  have to parse intent from generative LLM output.
- The forward-direction principle (new prose anchors on existing) and
  the reactive-direction principle (existing prose grandfathers unless
  factually wrong or clearly drifted) compose cleanly: the same cohort
  retrieval feeds both directions, and the skill carries the
  distinction.

**Negative.**

- Two new graph nodes (`gather_reference_metadata`,
  `classify_extraction_mode`) and two new MCP tools
  (`list_series_for_concept`, `list_provider_series_for_concept`) added
  to the v1 scope.
- One new value in the `change_proposal_item.action` enum
  (`suggest_human_apply`) and one new status value in
  `change_proposal_item.validation_status` (`pending_human_apply`,
  `applied_by_operator`), plus a small SQLAdmin affordance to mark items
  applied. These are small schema and admin additions but real ones.
- The proposal drafter is now responsible for two distinct kinds of
  output (new rows and harmonisation items) on the same call. The skill
  guides this; the failure mode if guidance is ignored is reviewer
  flags, not silent corruption.
- The seed exemplars in the metadata skill are operator-curated content
  that has to be reviewed and signed off before the skill graduates to
  `accepted`. Until then, the skill loads as `draft` only for
  documentation, not as live behavior.

## Alternatives considered

- **Route scenario 2 through Gate 2.** Rejected as a category error.
  Gate 2 governs identity corrections, where the danger comes from
  cross-row dependence on the identity field. Prose carries no such
  dependence. Routing prose through Gate 2 would both dilute Gate 2's
  meaning and overstate the risk of prose updates.
- **Introduce a third gate (Gate 1.5) for harmonisation.** Rejected.
  The risk profile of prose updates does not justify a third structural
  approval surface. Bundling as companion items on Gate 1 captures the
  same review attention without expanding the gate ceremony.
- **Defer harmonisation to a separate later session.** Rejected. The
  moment of recognition is during onboarding, when the cohort is loaded
  and the drafter has the context. Deferring loses that context; in
  practice the cleanup session never gets scheduled.
- **Item-level approval checkboxes at Gate 1.** Rejected. The
  `Request changes` path already provides selective rejection. Adding
  checkboxes complicates the approval surface and the state schema for
  a case that is rare in practice.
- **Treat all prose updates as freely-editable, drafter-discretion.**
  Rejected. Without structural backing, "don't change for changes' sake"
  is prompt discipline rather than a guarantee, and the failure mode is
  exactly the cosmetic-churn problem the operator explicitly flagged.
- **Hard-count thresholds for outlier triggers (e.g. ≥3 siblings).**
  Rejected. Magic numbers are procedural rather than domain knowledge
  and invite Goodhart effects (the drafter "finds" three agreeing
  siblings to launder a pre-formed opinion). Replaced with "requires a
  chorus; single-voice disagreement is not consensus" plus per-item
  evidence and reviewer judgment.
- **Curated `is_exemplar` flag on a `series` column.** Rejected for v1.
  Adding a column to mark certain series as canonical exemplars
  introduces governance overhead and a new entity to maintain. Skill-bundled
  exemplars achieve the same effect with no schema change and are
  loaded only when cohort A is empty.
- **Add `description` to `IngestionFeed` to give cohort C a feed-level
  anchor.** Rejected. Feeds are an execution concept per ADR 0010 / 0012;
  loading them with human prose pollutes the role they play in the
  runtime. Cohort C is built through `series_sources` instead.
- **Apply current hard rules retroactively to grandfathered prose.**
  Rejected. This is the same failure pattern as forcing every old
  `series.code` to be renamed when the code grammar evolves. Hard rules
  govern new prose; existing prose is grandfathered unless factually
  wrong. The pattern matches how identity is handled elsewhere in the
  system.

## Out of scope, deferred to follow-on work

- **Enum-gap escalation.** When the agent encounters a series whose
  structural shape cannot be captured by an existing enum value
  (frequency, measure, seasonal_adjustment, etc.), the right move is for
  the agent to surface the gap to the operator, pause, allow the
  operator to add the enum value in code and migrate, and resume the
  session with the new vocabulary visible. The design of that pause /
  resume / re-resolve mechanism is its own ADR-shaped decision and is
  not folded into this one.
- **Item-level "mark applied" workflow in SQLAdmin.** The new status
  values are introduced here; the SQLAdmin affordance is left for a
  small follow-on implementation slice that does not require ADR-level
  discussion.
- **Promotion of `skill-metadata-standardisation` from `draft` to
  `accepted`.** The skill is content-complete but the seed exemplars
  inside it must be reviewed by the operator before runtime use.
