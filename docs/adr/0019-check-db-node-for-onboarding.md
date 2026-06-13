# ADR 0019 — `check_db` node for catalog-duplicate detection in onboarding

**Status:** Proposed

**Date:** 2026-06-12

## Context

ADR 0011 ratifies the gated onboarding graph and ADR 0018 splits scoping
into three nodes (clarify → verify_identifier → brief writer). The brief
writer hands off a self-contained descriptive brief to the rest of the
graph. That brief is descriptive by construction: it carries concept,
geography, frequency, units, transformation, methodology, and provider
context, but it does not carry the canonical catalog code or series
UUID. By the time the brief lands, the only reliable input is prose.

Today the next downstream node is the proposal drafter. There is no
intervening check against the existing catalog. This creates three
failure modes that the gated workflow is supposed to prevent:

- **Silent duplication.** A series already represented in the catalog
  under a different name or alt-name gets re-onboarded as a new
  `series` row because the agent never compared the brief against
  catalog contents.
- **Trivial-transformation duplication.** A new series is registered
  whose only difference from an existing sibling is a transformation
  the existing catalog can already derive (e.g. index level vs YoY
  growth rate computable from that index).
- **Missed supersede opportunities.** A new series is registered that
  is a methodological upgrade over an existing series (e.g. a level
  series superseding a monthly-change series of the same concept),
  but the existing series is left in place rather than being marked
  for retirement or supersede.

These failure modes are not addressable by the proposal drafter alone:
the drafter writes a proposal for the brief it is given; it does not
shop the brief against the catalog. They are also not addressable by
human review at Gate 1 — the reviewer sees the proposal in isolation,
not the comparison set.

## Decision

Insert a new `check_db` node between brief writing and proposal
drafting. Its single responsibility is **catalog similarity detection
from descriptive input**.

### Position in the graph

```
… → verify_identifier → brief_writer → check_db → proposal_drafter → …
```

`check_db` is read-only with respect to the catalog. It does not
mutate state, does not gate, and does not interact with the user
directly. Its output is a structured verdict consumed by the next node
(or by a thin routing node) which then decides whether to abort the
session, confirm with the user, or proceed to drafting.

### Inputs

- The descriptive brief from the brief writer.
- The verification findings produced by `verify_identifier`, for
  orientation only.

### Output

A structured `CheckDbVerdict` with:

- `verdict`: a single classification of the strongest catalog
  relationship found, from a closed set: `no_match`, `duplicate`,
  `same_concept_other_feed`, `transformation_overlap`,
  `adjacent_supersede_candidate`, `distinct_with_related`.
- `similar_series`: the catalog candidates considered, each annotated
  with relation and a methodology-grounded rationale.
- `supersede_candidates`: subset where the briefed series is a
  methodological upgrade over an existing series.
- `findings.notes`: free-text on search coverage and any unrecognised
  methodology values the downstream nodes should know about.

### Routing semantics

The verdict drives the next-node behaviour:

- `duplicate` → propose to abort the session; the user may insist or
  ignore, but the default is abort.
- `same_concept_other_feed` → confirm with the user that they want a
  second source for the same concept before proceeding.
- `transformation_overlap` → confirm with the user; the default
  recommendation is to not ingest and instead derive from the existing
  sibling, but the user can override.
- `adjacent_supersede_candidate` → proceed to drafting **and**
  surface the supersede recommendation so the downstream proposal
  drafter can include a retire-or-supersede item for the existing
  series.
- `distinct_with_related` and `no_match` → proceed to drafting
  without user interaction.

Routing logic lives in a routing node (or conditional edge) that
consumes the verdict. `check_db` itself does not phrase user-facing
copy. This keeps the node's tool budget independent of UX wording.

### Catalog access

`check_db` reaches the catalog only through the read-only
`macrodb-mcp` server, consistent with ADR 0011. It does not connect to
Postgres directly, does not use raw SQL, and does not bypass the
semantic tool surface.

The tool surface required by this node is **similarity-based**,
because the brief carries no codes. The existing read-only MCP surface
is built around exact-key lookups (`lookup_concept(code)`,
`lookup_indicator(code)`, `find_sibling_series(indicator_id)`,
`list_series_for_concept(concept_id)`,
`list_provider_series_for_concept(provider_id, concept_id)`,
`list_enum_values(table, column)`) which cover drill-down but not
candidate retrieval from prose. The MCP is extended with a
similarity-search surface — `search_concepts`, `search_indicators`,
`search_series` — that internally combines a tag-based prefilter, a
cosine-similarity rerank over per-row embeddings, and full descriptive
payload in the returned candidates. The catalog-wide embedding
infrastructure that makes this possible (pgvector columns on
`concepts`, `indicators`, `series`; an `embed_text` wrapper around
the OpenAI embeddings API pinned to `text-embedding-3-small` at 1536
dimensions; a service-function registration path that owns
embed-on-write; and a `macrodb embeddings backfill` CLI) is ratified
separately in ADR 0020. `check_db` consumes that surface; it does not
own its design.

### What `check_db` is not

- It is not a research node. It does not call `web_search`. Its
  source of truth is the catalog only.
- It is not a proposal drafter. It does not draft series, family, or
  concept rows.
- It is not a gate. The human approval gates (1 and 2) operate over
  proposal artifacts, not over verdicts.
- It is not an enum-gap escalator. If it encounters a methodology
  value the catalog cannot express, it records the observation in
  `findings.notes`; the existing enum-gap path (ADR 0014) handles the
  escalation downstream.

## Consequences

**Positive:**

- Silent duplication and trivial-transformation duplication are no
  longer possible at the catalog level — the drafter only sees briefs
  the catalog has been checked against.
- Supersede candidates surface automatically rather than being
  discovered by accident during human review.
- The node's contract is a structured verdict, which is observable,
  testable, and replayable from a LangGraph checkpointer.
- Routing logic is decoupled from search logic; UX wording can change
  without re-running similarity searches.

**Negative / risks:**

- Recall depends on the quality of the candidate-retrieval surface
  exposed by the MCP (ADR 0020). False negatives surface as duplicates
  that slip through.
- Search budget is bounded (cap of 6 calls); a brief with many
  plausible neighbours may exhaust budget before finding the
  duplicate. Mitigated by the routing node falling back to human
  confirmation when the verdict is borderline.
- The `transformation_overlap` and `adjacent_supersede_candidate`
  classifications encode opinionated normalisation rules (e.g. "do
  not register YoY alongside the index level"). These rules must be
  documented as a skill loaded by the node, so they remain editable
  without code changes.
- Embedding-input composition is the more sensitive design choice
  than the model selection. If the function that builds the embed text
  from a row changes, every existing row's embedding becomes stale.
  This is tracked and mechanically detected via the
  `embedding_input_hash` column ratified in ADR 0020; `check_db` is a
  consumer of that mechanism, not its owner.

**Out of scope for this ADR:**

- The catalog-embedding infrastructure (pgvector columns, model
  selection, embed-on-write service path, backfill CLI). Ratified in
  ADR 0020.
- The supersede-execution mechanics (how an old series is marked
  retired or pointed at the new one). Tracked separately under
  governance.
