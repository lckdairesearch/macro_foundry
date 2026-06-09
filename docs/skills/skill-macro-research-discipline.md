# skill-macro-research-discipline

**Status:** stub

## Scope

What the researcher should search for, fetch, and verify when investigating
a new source. Covers the macroeconomic-specific research checklist
(methodology, frequency, seasonal adjustment, vintage policy,
publication cadence) and the "weirdness detection" duty added in the
workflow doc.

This skill is provider-agnostic and tool-agnostic: it describes the
discipline, not the search tool. The web-search capability is assumed
available to the model (built-in for v1's OpenAI binding).

## When triggered

- node is `research` (always, on first invocation)
- node is `data_correctness_review` (for cross-reference web fetches)

## Body

To be written. Should cover: the macroeconomic-specific verification
checklist (methodology section, publication frequency vs. standard for
the concept, units and scale, seasonal adjustment label, vintage and
revision policy, base year for index series, currency basis); the
weirdness-detection duties (non-standard request encoding, response
wrappers that differ between data and error states, dimension semantics
encoded in code padding or magic values, mixed-type fields, multi-language
fields, pagination quirks); guidance on cross-referencing the provider's
self-published page against at least one independent source for
concept-level verification; and the rule that web fetch is for
human-readable provider pages, not for scraping data as a substitute for
proper ingestion.
