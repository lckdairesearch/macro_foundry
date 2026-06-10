# `runners/` — deprecated

Per-provider runners were replaced by the generic runtime + selector registry under
`../runtime/` per [ADR 0012](../../../../docs/adr/0012-selector-registry-ingestion-runtime.md)
and [issue #35](https://github.com/lckdairesearch/macro_foundry/issues/35).

**Do not add new runners here.** New providers should be wired as selector
configurations under `runtime/`.
