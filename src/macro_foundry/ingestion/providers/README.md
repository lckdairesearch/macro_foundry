# `providers/` — sunset after slice #20

Per-provider HTTP clients used by the legacy runners. Being replaced by
selector-owned fetch logic under `../runtime/` per
[ADR 0012](../../../../docs/adr/0012-selector-registry-ingestion-runtime.md)
and [issue #19](https://github.com/lckdairesearch/macro_foundry/issues/19).

**Do not add new provider clients here.** New providers fetch through
their selector's `fetch` method. This directory is removed after the
FRED migration completes.
