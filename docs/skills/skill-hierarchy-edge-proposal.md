# skill-hierarchy-edge-proposal

**Status:** stub

## Scope

Evaluating candidate `series_hierarchy_edges` between real canonical
`series` rows. Covers the same-concept default, the cross-concept escalation
rule, the no-hidden-placeholders principle, and the additive-enrichment
contract from ADR 0010 and `docs/series_catalog_governance.md`.

This skill does not cover hierarchy *write* semantics during routine
refreshes (those are forbidden at the workflow level) or canonical identity
decisions for the parent or child themselves.

## When triggered

- node is `draft_proposal`, `governance_review`, or
  `dangerous_correction_plan`
- `proposal.hierarchy_edges` is non-empty, or
  `existing_catalog_hits.candidate_parent_series` is non-empty during
  research

## Body

To be written. Should cover: same-concept default in operational form;
what counts as a "real published" canonical series eligible for a
hierarchy edge; rejection criteria for hidden placeholder nodes; how
ragged depth interacts with provider tree layouts; the rule that parent
observations remain stored as published values even when children and
aggregation rules exist; cross-concept proposal review path; and worked
examples (CPI headline → CPI components as same-concept; GDP → household
consumption as cross-concept requiring explicit approval).
