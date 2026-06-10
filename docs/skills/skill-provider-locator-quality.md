---
status: stub
---
# skill-provider-locator-quality

**Status:** stub

## Scope

Assessing the quality of `series_sources.external_code` and
`series_sources.ref_url`. Covers what counts as a strong, weak, or missing
provider locator and how that quality should be surfaced to reviewers and
to the human gate. Pulls from `docs/series_catalog_governance.md`'s "Weak
provider locator governance" section.

This skill does not cover provider mapping decisions (which provider should
be the primary, redistributor, harmonized, etc.) or the request-level feed
linking decision.

## When triggered

- node is `research`, `draft_proposal`, or `governance_review`
- `proposal.candidate_series_source` is populated and the agent is
  about to write or review the locator fields

## Body

To be written. Should cover: signals of weak `external_code` (reused
dataset code, table code instead of leaf, ambiguous provider label,
missing entirely); signals of weak `ref_url` (broad portal URL, dead link,
behind login wall); when nullable is appropriate (genuinely
locator-less providers) vs. when nullable is a smell; and how weak locators
flow into `weak_locator_flags` in graph state and into reviewer findings.
