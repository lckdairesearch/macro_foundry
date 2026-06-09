# skill-dangerous-correction

**Status:** stub

## Scope

When the workflow should branch into the Gate 2 dangerous-correction path
versus continuing with ordinary onboarding. Covers the publication-boundary
test, the three triggers (researcher-detected identity problem, reviewer
diagnosis, uniqueness collision the operator chooses to challenge), and the
shape of the repair plan that a dangerous-correction proposal must carry.

This skill does not cover ambiguity in *not-yet-published* identity
decisions (see [skill-ambiguity-handling](skill-ambiguity-handling.md)).

## When triggered

- node is `research`, `governance_review`, `approval_parse`, or
  `dangerous_correction_plan`
- `state.is_dangerous_correction` is True, or
  `state.approval_parse.intent == "challenge_existing"`, or research
  surfaces a published series whose identity appears materially wrong

## Body

To be written. Should cover: publication-boundary test (what counts as
"already published"); the three trigger conditions; the rename-in-place vs.
supersede-and-replace vs. route-future-only options and when each applies;
the affected-rows impact analysis the planner must produce (source
mappings, feeds, observations, derivations); the Gate 2 picker phrasing
and the heightened approval expectations; and the constraint that
dangerous-correction execution scope is limited to the approved repair
plan only.
