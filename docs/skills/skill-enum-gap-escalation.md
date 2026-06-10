# skill-enum-gap-escalation

**Status:** draft

The body is content-complete; the skill is held at `draft` until the
runtime exists to load it and the operator confirms the rendered
operator-instruction block at `enum_gap_wait` matches the project's
preferred Alembic invocation. Promote to `accepted` after that
review.

## Scope

How the proposal drafter recognises and reports a structural enum-gap
— a candidate series whose real-world methodology cannot be
faithfully represented by the existing values of one of macrodb's
series-methodology enums — and the discipline for when an
`EnumGapProposal` may be emitted versus when the drafter must pick
the closest existing value.

This skill governs enum-value gaps only. It does not cover
column-shaped gaps (methodological distinctions macrodb has not
modelled at all); those abort with reason `schema_deficiency` and
are addressed in a separate operator-led design pass.

The architectural rationale for this skill, the
`enum_gap_proposals` state field, the `enum_gap_wait` node, the
`suggest_enum_addition` action, and the audit-row design lives in
[ADR 0014](../adr/0014-enum-gap-escalation.md).

## When triggered

- node is `draft_proposal` and the drafter is about to populate any
  field bound to one of the allowlisted enums (see below), OR
- node is `governance_review` and the proposal under review carries a
  non-empty `enum_gap_proposals` list (the reviewer evaluates whether
  each gap meets the discipline bar before the operator sees it)

## Body

### The allowlist

The drafter may emit an `EnumGapProposal` against any of these enums,
all in [src/macro_foundry/enums/series.py](../../src/macro_foundry/enums/series.py):

`Frequency`, `SeasonalAdjustment`, `Measure`, `MeasureHorizon`,
`UnitKind`, `UnitScale`, `PriceBasis`, `ReferenceKind`,
`TemporalStockFlow`.

It may not emit gaps against any other enum. `OriginType` is
intentionally excluded — it describes how macrodb produces
observations, not what the series measures. Governance, provider,
derivation, run, and geography enums are macrodb's own control
vocabulary; gaps there are architecture decisions, not onboarding
escalations.

### The three conditions (all required)

A gap may be emitted only when all three of these hold. The drafter
must be able to articulate each one before the proposal is allowed
to leave the drafter.

1. **No existing value fits.** The drafter has considered every value
   in the enum and articulated, per value, why it does not represent
   the candidate series faithfully. Emitting a gap because "the
   closest value is awkward" or "the existing values are unclear" is
   not allowed — only "none of these means what the provider's
   methodology means."
2. **The distinction matters for catalog identity.** The
   methodological distinction the gap captures is one that downstream
   consumers (analysts querying the catalog, derived series, the
   `latest_observations` view) would care about. Distinctions
   absorbable into `description` prose without losing query semantics
   stay in prose.
3. **The provider's documentation supports it.** The gap reflects
   something the provider explicitly publishes, not the drafter's
   inference. Provider says "trend-cycle adjusted, distinct from
   seasonally adjusted" → gap is real. Provider's terminology is
   ambiguous → no gap; pick the closest existing value and flag the
   ambiguity in the proposal summary for human review.

### Per-proposal evidence structure

Every `EnumGapProposal` must carry, at minimum:

- `enum_path` — fully-qualified Python path of the enum class (e.g.
  `macro_foundry.enums.series.SeasonalAdjustment`)
- `proposed_value` — the literal string value (e.g. `"BSA"`)
- `proposed_name` — the symbolic Python identifier (e.g. `BOTH_SA`)
- `existing_values_considered` — a mapping from each existing enum
  value to a one-line dismissal explaining why it does not fit. An
  empty or partial walk is evidence of laziness, not of a real gap.
- `provider_evidence` — a cited URL plus the snippet from the
  provider's documentation that establishes the distinct
  methodology. Inferred or paraphrased evidence does not count.
- `catalog_impact` — one line on why the distinction matters for
  queries. This is the condition-2 justification, in writing.
- `rationale` — one line, ≤200 characters, referencing the evidence

Proposals with missing or empty evidence fields are **dropped before
the gap signal is set on graph state**. The drafter then falls back
to coercion-with-rationale: it picks the closest existing value, and
records the reasoning in the proposal summary so the human can flag
it at Gate 1 if the coercion was wrong.

The drop-on-missing-evidence rule means the drafter does the same
amount of work either way. The only difference between "real gap"
and "lazy gap" is whether the work yields an escalation or a
documented coercion.

### Anti-patterns (never proposable as gaps)

The following are anti-patterns and never justify an `EnumGapProposal`,
regardless of how the drafter would phrase the rationale:

- **The existing value's symbolic name is clunky or unclear.** This
  is a cosmetic complaint about macrodb's vocabulary, not a real
  methodological gap.
- **The provider uses a different word for the same concept.** This
  is a synonym, not a new methodology. `index level` vs `level value`
  is not a `Measure` gap.
- **The provider exposes the methodology as a free-text field rather
  than a controlled list.** Free-text methodology encodes in
  `description` prose; it does not become a new enum value.
- **The distinction is only present in a minority of providers and
  is not standard in macroeconomic practice.** Not catalog-worthy.
  Examples include vendor-proprietary adjustment methods used only
  by one source.
- **The drafter is uncertain which existing value applies.**
  Uncertainty is not a gap. Either pick `unknown` if the enum has it,
  flag the ambiguity in the proposal summary for human review, or
  surface the question in chat — none of these are
  `EnumGapProposal` shapes.
- **The structural distinction can be recorded in `variant` or
  `description` without losing query semantics.** Then it should be,
  per the metadata-standardisation skill.

The anti-pattern list exists because each item is a known failure
mode where the drafter pattern-matches on "the existing values don't
feel right" and emits an interrupt for nothing. Every false-positive
gap costs the operator an interruption.

### Multi-gap detection in one pass

When the drafter populates the candidate series' enum-typed columns,
it evaluates the candidate against the full allowlist in one pass
and emits every gap it finds, not just the first. The
`enum_gap_proposals` field is list-shaped exactly so multi-gap
sessions can be addressed in one operator pause.

The drafter must not stop at the first gap. Doing so creates
multi-pause sessions ("apply, resume, hit gap 2, apply, resume, hit
gap 3...") which is worse UX and erodes operator trust.

### The coerce-with-explanation branch

When the operator picks `Decline and coerce` at `enum_gap_wait`, the
graph re-runs the drafter with two new state fields populated:

- `coerce_hints: dict[str, str]` — `enum_path` → operator-chosen
  existing value
- `coerce_rationales: dict[str, str]` — `enum_path` → operator's
  free-text rationale

On re-run, the drafter:

1. **Uses the operator-chosen value** for any column whose
   `enum_path` appears in `coerce_hints`.
2. **Does not re-emit** an `EnumGapProposal` for any `enum_path`
   already in `coerce_hints`. The operator has spoken.
3. **Does not write** a coercion note into `series.name` or
   `series.description`. The audit row in `change_proposals`
   preserves the original gap, the operator's chosen coercion, and
   the rationale. The catalog row reflects the operator's curatorial
   decision; future queries against the chosen value correctly
   include this series.

If the operator wants a prose note explaining the coercion, they add
it themselves at Gate 1's `Request changes` path.

### Reviewer scope

The governance reviewer, when it sees a non-empty
`enum_gap_proposals` list on the drafter's output, evaluates each
gap against the three conditions and the anti-pattern list. Weak
gaps become reviewer flags (visible to the operator at the wait
node), not silent drops. The operator at the wait node is the final
arbiter; the reviewer's role is to surface laziness or
anti-pattern-shaped gaps the drafter slipped through.

### Examples of legitimate gaps

These are reference examples for "this is what a real gap looks like."
They are not anchors for new gap emission; the discipline above is.

- A provider publishes a trend-cycle-adjusted (TCA) series, distinct
  from `SA`, `SAAR`, `NSA`. Provider docs cite the X-13ARIMA-SEATS
  trend-cycle component explicitly. `SeasonalAdjustment` cannot
  represent it; coercing to any of the existing values would
  misclassify it. Real gap.
- A provider publishes a 10-day "dekad" frequency (common in agricultural
  statistics from some African statistical offices). `Frequency`
  values `D, W, M, Q, S, A` do not include it. Provider docs
  describe the 10-day reporting cycle as standard for the dataset.
  Real gap.
- A provider publishes a chain-linked price basis distinct from
  `nominal`, `real`, `ppp`, `other`. Provider docs cite the chain
  methodology and a base period; the distinction matters for derived
  series doing nominal/real decompositions. Real gap.

### Examples of non-gaps (look like gaps; aren't)

- The provider's `seasonal_adjustment` column reads "Smoothed".
  Provider docs describe a moving-average smoothing applied to NSA
  data. This is a description of NSA data with a smoothing transform,
  not a new adjustment kind. Use `NSA` and record the smoothing in
  `series.description`. Not a gap.
- The provider distinguishes "Annual (calendar year)" from "Annual
  (fiscal year)". `Frequency` already records the period; the
  fiscal-vs-calendar distinction belongs in `variant` and
  `description`. Not a gap.
- The drafter cannot tell whether the series is `level` or `index`.
  Uncertainty is not a gap. Use the best inference, flag in the
  proposal summary, and let the human resolve at Gate 1.

## Notes for the reader of this skill

- The asymmetry between conditions (all three required) and
  anti-patterns (any one disqualifies) is deliberate. The structural
  bar is high because every false-positive gap is an operator
  interruption.
- This skill composes with `skill-metadata-standardisation`. When a
  distinction is real but not catalog-worthy, the metadata skill is
  where it goes (in `description` and `variant` prose). When it is
  catalog-worthy and no existing value fits, this skill applies.
- The single-developer project context shapes the design. A
  multi-developer setting might add a reviewer-side veto or a
  separate enum-governance role. For now, the operator is the final
  arbiter at the wait node and the audit row records what they
  decided.
