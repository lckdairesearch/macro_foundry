# `runners/` — sunset after slice #20

This directory holds the per-provider runners used today (FRED). It is
being replaced by the generic runtime + selector registry under
`../runtime/` per [ADR 0012](../../../../docs/adr/0012-selector-registry-ingestion-runtime.md)
and [issue #19](https://github.com/lckdairesearch/macro_foundry/issues/19).

**Do not add new runners here.** New providers should be wired as
selector configurations under `runtime/`. The FRED runner stays in place
until its migration slice lands; after that, this directory is removed.
