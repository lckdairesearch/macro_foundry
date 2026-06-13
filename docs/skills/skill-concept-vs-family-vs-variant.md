---
status: stub
---
# skill-concept-vs-family-vs-variant

**Status:** stub

## Scope

The decision rule for whether a new arrival should be a new `concept`, a
new `indicator`, or a new `series` variant within an existing indicator.
Codifies the governance from `docs/series_catalog_governance.md` and the
glossary entries in `CONTEXT.md` (concept, indicator, series, indicator
variant, default variant).

This skill does not cover canonical code grammar (see
[skill-canonical-code-grammar](skill-canonical-code-grammar.md)) or
provider mapping (which lives entirely in `series_sources`, not in canonical
identity).

## When triggered

- node is `research`, `draft_proposal`, or `governance_review`
- `proposal.candidate_series_code` or `proposal.candidate_concept_code`
  is populated, or `ambiguity_flags` contains an entry of
  `kind == "identity_scope"`

## Body

To be written. Should cover: the geography-neutrality test for concepts;
the one-concept-one-geography rule for indicators; when methodology
differences justify a sibling series vs. a new indicator vs. a new concept;
the default-variant pattern and when it is appropriate to use it; the
publication-boundary rule that makes identity decisions sticky once
crossed; and worked examples (US CPI headline vs. core as one indicator;
US GDP nominal vs. real as one indicator; household-basket CPI variants as
sibling series with explicit variant tokens).
