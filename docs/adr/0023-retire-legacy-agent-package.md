# ADR 0023 — Retire the legacy `agent` package; `onboarding_agent` is canonical

**Status:** Accepted (amends ADR 0021)

**Date:** 2026-06-13

## Context

`macro_foundry` has carried two agent implementations.

The original gated-onboarding agent lived at `src/macro_foundry/agent`. Its
design is recorded across ADRs 0011, 0013–0016, and 0018. That package has been
renamed to `src/macro_foundry/depreciated_omit_this_agent` and is no longer
maintained, no longer on any live code path, and slated for deletion.

A second, replacement agent is under active construction at
`src/macro_foundry/onboarding_agent` — the `check_db` node (ADR 0019), the
scoping nodes (ADR 0018), the MCP chat spike (`mcp_chat.py`), and the prompts.
All new agent work targets this package.

During the `series_family → indicator` rename (ADR 0021, issues #68–#71) the
legacy package was deliberately excluded from every edit (ADR 0021 line 118).
As a consequence it now actively contradicts the current system:

- it speaks the retired `family` / `series_family` / `is_primary` vocabulary;
- it imports modules that have been renamed or deleted (e.g. the live
  `mcp/write_tools.py` Path A `propose_create_series` does
  `from macro_foundry.agent.proposal import DraftProposal`, which no longer
  resolves — the path is dead);
- its `DraftProposal` / draft-member schemas and proposal grammar predate the
  current proposal flow.

An agent or human reading that directory — or the ADRs that describe it — will
find statements that conflict with the schema, the domain vocabulary, and the
`onboarding_agent` design. We need an explicit precedence rule so stale content
is not propagated into new work.

Separately, ADR 0021's consequences claim (line 82–83) that the in-place rename
migration preserves "existing rows and **embeddings**" turns out to be wrong for
embeddings, and that error should be on record.

## Decision

1. **The legacy package is retired.** `src/macro_foundry/depreciated_omit_this_agent`
   (formerly `src/macro_foundry/agent`) is excluded from all sweeps, renames, and
   maintenance. It will be deleted in a future cleanup once nothing references it.

2. **`src/macro_foundry/onboarding_agent` is the single canonical agent.** All new
   agent work goes there. No new code, prompt, schema, or doc should import from or
   model itself on the retired package.

3. **Precedence rule.** Where the retired package — its code, comments, prompts, or
   any doc/ADR text describing *its implementation* — contradicts the current
   schema, domain vocabulary (`CONTEXT.md`), an accepted ADR, or the
   `onboarding_agent` design, the retired package is authoritatively **wrong** and
   must be deprioritised. Do not carry its `family`-era vocabulary, its
   `DraftProposal` grammar, or its proposal/draft schemas into new work.

4. **Older ADRs remain historical.** ADRs 0011, 0013–0016, and 0018 stay accepted
   as records of decisions made. Where their *implementation details* point at the
   retired `agent` package, treat those details as superseded by the
   `onboarding_agent`'s actual design — the decisions stand, the wiring does not.

5. **Dead importers are rewrite-or-delete, not preserve.** Live code that still
   reaches into the retired package — `mcp/write_tools.py` Path A, plus the broken
   standalone `scripts/embeddings_sanity.py` and `cli/onboard.py` import chain — is
   to be rewritten against `onboarding_agent` or removed during that build, not
   kept working against the legacy schema.

6. **Amendment to ADR 0021 (embeddings).** ADR 0021 states the in-place rename
   migration preserves existing rows *and embeddings*. The row-preservation claim
   holds. The **embedding-preservation claim does not.** The indicator recipe-label
   corrections that accompanied the rename (`Type: SeriesFamily → Type: Indicator`
   on indicators, `Family: → Indicator:` on series; ADR 0020 recipe) change the
   composed embedding-input text, so the stored vectors for `indicators` and
   `series` are stale. Correction: **embeddings are not preserved across the
   indicator rename.** A re-embed is required, and because there is no production
   embedding state worth conserving, a **full re-embed of all catalog embeddings**
   (`concepts`, `indicators`, `series`) may be run wholesale rather than a scoped
   backfill — whichever is simpler operationally is acceptable.

## Consequences

- Readers and agents get an unambiguous source-of-truth rule; the retired package
  cannot quietly reintroduce `family`-era vocabulary or schemas into new work.
- The embeddings correction is on record, so no one trusts stale vectors or the
  "embeddings preserved" line in ADR 0021. Semantic search results should not be
  trusted until a re-embed has run.
- Follow-on cleanup remains open and is tracked separately: delete the retired
  package once `onboarding_agent` no longer cribs from it; rewrite or delete
  `mcp/write_tools.py` Path A, `scripts/embeddings_sanity.py`, and the
  `cli/onboard.py` import chain.

## Alternatives considered

- **Edit the legacy package to the new vocabulary.** Rejected. Wasted effort on
  code slated for deletion; the directory was explicitly directed to be left
  untouched.
- **Delete the legacy package now.** Rejected for the moment. The
  `onboarding_agent` build still references it while under construction; delete once
  that dependency is gone.
- **Amend ADR 0021 in place to fix the embeddings line.** Rejected. ADRs are
  immutable once accepted (`docs/adr/README.md`); corrections live in a superseding
  or amending ADR, with the index noting the amendment — the ADR 0015-amends-0011
  precedent.
- **Scoped embeddings backfill only, no full re-embed.** Rejected as the *framing*.
  A scoped backfill is sufficient, but stating that a full re-embed is acceptable
  removes any ambiguity about whether the old vectors can be trusted: they cannot.
