# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Layout

This is a single-context repo.

Read before starting work:

- `CONTEXT.md` at the repo root
- `docs/adr/` at the repo root, focusing on ADRs relevant to the work

## Use the glossary's vocabulary

When your output names a domain concept, use the term as defined in `CONTEXT.md`.
Do not silently drift to synonyms that the glossary avoids.

## Flag ADR conflicts

If proposed work contradicts an existing ADR, surface that explicitly rather than silently overriding it.
