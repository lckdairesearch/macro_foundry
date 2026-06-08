# macro_foundry

`macro_foundry` is a macroeconomic database system. This repository is being
bootstrapped around the structure defined in `docs/architecture.md`.

## Start here

- Claude entrypoint: `CLAUDE.md`
- Codex entrypoint: `AGENTS.md`
- Agent operating manual: `AGENTS.md`
- Project scope: `docs/project_overview.md`
- Architecture: `docs/architecture.md`
- Code standards: `docs/code_standards.md`
- Build plan: `docs/build_plan.md`
- Progress tracker: `docs/progress_tracker.md`
- ADR index: `docs/adr/README.md`

## Current focus

Phase 3 Config + session + base: add typed settings, the async SQLAlchemy
engine/session wiring, and the shared ORM base mixins.

The canonical agent instructions live in `CLAUDE.md` and `AGENTS.md`.
