---
status: stub
---
# skill-ambiguity-handling

**Status:** stub

## Scope

The "ambiguity stays in proposal space" rule. Covers what counts as
identity-level ambiguity, what counts as ordinary uncertainty the agent
should resolve via best-effort inference, and how flagged ambiguities flow
through the graph as `ambiguity_flags`.

This skill does not cover correction discipline for *already published*
series with newly discovered identity problems (see
[skill-dangerous-correction](skill-dangerous-correction.md)).

## When triggered

- node is `research`, `draft_proposal`, or `governance_review`
- the agent is about to populate `proposal.candidate_series_code` or
  `proposal.candidate_concept_code` and the supporting evidence is not
  unambiguous

## Body

To be written. Should cover: the distinction between identity-level
ambiguity (must stop and propose) and peripheral uncertainty (can infer
and flag); examples of identity-level ambiguity (which CPI population
basis, which sectoral scope, which currency basis when provider and
canonical conventions disagree); the prohibition against minting a
canonical draft row in the main catalog to "reserve" a name during
proposal space; and how to phrase a clarification question that grills the
operator with the minimum specificity needed to resolve the ambiguity.
