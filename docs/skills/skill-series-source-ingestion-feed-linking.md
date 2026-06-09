# skill-series-source-ingestion-feed-linking

**Status:** stub

## Scope

When a candidate `series_source` can attach to an existing `ingestion_feed`
via a new `ingestion_feed_member` versus when a new request-level feed is
required. Covers the request-level model (ADR 0010), the fan-out semantics
(one feed, many members for shared payloads), and the practical signals that
distinguish the two cases.

This skill does not cover canonical identity decisions (see
[skill-concept-vs-family-vs-variant](skill-concept-vs-family-vs-variant.md))
or provider locator quality (see
[skill-provider-locator-quality](skill-provider-locator-quality.md)).

## When triggered

- node is `research`, `draft_proposal`, or `governance_review`
- `proposal.candidate_series_source` is populated
- the candidate provider already has at least one existing
  `ingestion_feed` in `existing_catalog_hits`

## Body

To be written. Should cover: the request-level definition from ADR 0010;
when a shared payload justifies reusing a feed; the role of
`feed_method`, `endpoint_url`, and `request_params` in identifying the
"same request"; the case for a new feed when execution semantics differ
(different auth, different rate-limit class, different schedule cadence);
and worked examples from FRED (one-member feeds), e-Stat (multi-member
shared payloads), and CenStatD (LZ-string-encoded dimension fan-out).
