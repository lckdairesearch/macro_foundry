# skill-canonical-code-grammar

**Status:** stub

## Scope

The `<geo>_<concept>_<variant?>_<freq>_<sa>_<measure>` slot grammar for
`series.code`. Covers slot order, token conventions, compound variant
handling, parsing expectations, and the prohibition against encoding
provider identity into the canonical code. Pulls from
`docs/series_catalog_governance.md`.

This skill does not cover *which* family or concept a code belongs to
(that decision lives in
[skill-concept-vs-family-vs-variant](skill-concept-vs-family-vs-variant.md)).

## When triggered

- node is `draft_proposal` or `governance_review`
- `proposal.candidate_series_code` is being constructed or validated

## Body

To be written. Should cover: the slot definitions; the fixed suffix
(`<freq>_<sa>_<measure>`) and right-parsing rule; the longest-known
concept-code match for resolving the middle of a code; compound variant
handling with separated tokens (e.g., `CORE_1P_HH`, not `CORE1PHH`); the
default-variant omission case; common anti-patterns (provider tickers,
reordered slots, ad-hoc abbreviations); and worked examples from the FRED
preset (US_GDP_NOMINAL_Q_SAAR_LEVEL, US_CPI_CORE_M_SA_LEVEL).
