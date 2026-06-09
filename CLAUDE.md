# macro_foundry — Agent Operating Manual

This file is read first by any agent (Claude Code, Codex, or otherwise) before any work.
The same content lives in both `CLAUDE.md` and `AGENTS.md` at the project root so both
tools find their entry point.

## Core principle

You are working on **macro_foundry**, a macroeconomic database system. The architecture
decisions, schema, domain language, and build plan have all been settled in advance.
Your job is to execute against them faithfully, not to re-decide them.

If a request appears to contradict what's documented here, **STOP and ask the user**.
Never silently assume. Never invent a decision. Never substitute your preferences for
the ones already made.

## What to read, in order

Before any work, load these files. They are short by design — read all of them.

1. `docs/project_overview.md` — what macro_foundry is, and the scope of the current phase
2. `docs/architecture.md` — the stack, layers, and decisions
3. `CONTEXT.md` — domain language (series vs series_family vs concept vs observation, etc.)
4. `docs/code_standards.md` — rules that apply to every line of code
5. `docs/build_plan.md` — the phased implementation plan
6. `docs/progress_tracker.md` — what's done, what's next
7. `docs/adr/` — skim the index; read in full any ADR relevant to the work at hand

For schema work, the **canonical source** is `docs/schema/db_er.txt` (V3 eraser.io source).
SQLAlchemy models, Alembic migrations, Pydantic schemas, and tests must all agree with V3.
If a discrepancy is found, V3 is the source of truth — flag the discrepancy and propose
the fix.

## Guardrails — non-negotiable rules

These rules are settled. Do not relitigate them in code without an ADR-level discussion
with the user.

- **No lazy loading.** Async SQLAlchemy. All relationships are eager-loaded with
  `selectinload` or `joinedload`. If you see `MissingGreenlet` in an error, this is
  the cause.
- **No native Postgres `ENUM` types.** Use Python `str, Enum` classes plus
  `SAEnum(MyEnum, native_enum=False, name="ck_<table>_<col>")`. The DB enforces values
  via a named CHECK constraint.
- **No DB triggers.** Use SQLAlchemy `onupdate=func.now()` at the ORM layer for
  `updated_at`. We need Neon-portable behavior.
- **No `asyncpg`.** We use `psycopg3` async (`postgresql+psycopg://...`). Sync and
  async share the same driver family.
- **No `pg_cron`.** Schedules in `ingestion_feeds.cron_schedule` are metadata read by
  an external scheduler. Never wired to in-DB cron.
- **No `localStorage`/`sessionStorage`** — not applicable to this phase (no frontend yet),
  but flag for the future.
- **Migrations run as `macrodb_owner`. Everything else (FastAPI, SQLAdmin, ingestion,
  tests) runs as `macrodb_app`.** Never mix the two roles.
- **No PostgREST, no Supabase, no Hasura, no Django, no SQLModel, no TimescaleDB.**
  These were all considered and rejected with reasoning in ADRs. Do not propose them.
- **No prematurely created skills, abstractions, or libraries.** If you find yourself
  wanting to extract something, propose it first; do not silently build it.

## Updating documentation

When you complete a phase or make a non-trivial decision:

1. **Update `docs/progress_tracker.md`** with what was done, dated, with any notes
   on deviations from the build plan.
2. **If a new architectural decision was made**, write an ADR at
   `docs/adr/00XX-title.md` following the existing format (see ADRs 0001–0006).
3. **If the domain language evolved**, update `CONTEXT.md`.
4. **If the build plan changed**, update `docs/build_plan.md`.

Do not silently change architecture decisions. If you encounter a reason to deviate
from `architecture.md`, **stop and discuss with the user before changing it**.

## Operating cadence

- One phase at a time per session, where possible.
- Verify each phase against its `build_plan.md` acceptance criteria before moving on.
- Tests are part of the deliverable, not an afterthought. Phase 12 is dedicated to
  them, but inline tests are welcome throughout the build.
- When in doubt about scope, do less, not more. Confirm with the user before expanding.

## Commit messages

When making a commit, write the message for a developer who understands the
macro_foundry domain but has not read the diff yet.

Use this format:

`<type>(<scope>): <what changed>`

Optional body:

- why this change was needed
- the key behavioral, schema, or architectural impact
- any important constraint, tradeoff, or follow-up

Rules:

- Use the imperative mood: `add`, `fix`, `rename`, `enforce`, `wire up`.
- Keep the subject specific and readable in isolation.
- Prefer scopes such as `db`, `models`, `schemas`, `api`, `seed`, `admin`,
  `tests`, `docs`, `agents`.
- Describe the intent and effect, not the editing mechanics.
- Mention user-visible behavior, schema impact, or architectural impact when relevant.
- Do not write vague subjects like `update stuff`, `misc fixes`, `wip`, or
  `address comments`.
- Do not turn the body into a file list or patch summary.
- If the commit changes a settled architectural decision, stop and discuss it
  with the user before committing.

Use these types when they help: `feat`, `fix`, `refactor`, `test`, `docs`,
`chore`. Do not force a type if it makes the message worse.

Examples:

- `feat(db): add async session factory with Neon-safe pool settings`
- `fix(models): enforce currency_code for currency-denominated series`
- `docs(agents): clarify two-role database rule for migrations`
- `test(api): cover latest_observations route with vintage revisions`

## Agent skills

### Issue tracker

Issues are tracked in this repo's GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

The repo uses the default Pocock triage label vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo with one root `CONTEXT.md` and root `docs/adr/`. See `docs/agents/domain.md`.

## Skills (Pocock)

Installed via `npx skills@latest add mattpocock/skills`. Use them where they fit:

- **`/grill-with-docs`** — before any non-trivial change; surfaces assumptions, updates
  `CONTEXT.md` and ADRs inline. The single most valuable skill in the set.
- **`/tdd`** — for test work, especially Phase 12. Red-green-refactor, no skipping.
- **`/diagnose`** — when something breaks. Enforces reproduce → minimize → hypothesize →
  fix → regression-test. Do not spiral.
- **`/zoom-out`** — when you're deep in one file and need to remember the larger system.

Other Pocock skills (`/to-prd`, `/to-issues`, `/triage`, `/improve-codebase-architecture`,
`/prototype`, `/handoff`, `/caveman`) are not installed yet. Add them only if a real
need surfaces.

## Style for agent output

- Be concise. The user dislikes filler, over-apologizing, and ceremony.
- When asked a yes/no question on a settled topic, answer yes/no with one-line reasoning.
- When the user is right and you were wrong, concede explicitly and move on.
- Push back when the user is wrong, with reasoning, but do not litigate to the death.
- Don't suggest features outside the current phase unless asked.

## Agent skills

### Issue tracker

GitHub Issues for this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default Pocock label mapping. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo with root `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.
