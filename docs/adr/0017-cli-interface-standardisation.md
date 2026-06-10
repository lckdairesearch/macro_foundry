# ADR 0017 — `macrodb` CLI interface standardisation

**Status:** Accepted

**Date:** 2026-06-10

## Context

The `macrodb` CLI grew command-by-command as phases landed (`seed`,
`serve`, `bootstrap`, `onboard`, plus the two MCP console scripts). Each
command was written in isolation, so the surface is internally
inconsistent in ways that make it harder to learn, script against, and
extend:

1. **"Which database" is modelled three different ways.** The same
   idea — where does this command point — appears as `--database`
   (`DatabaseTarget`: `app`/`test`), `--target` (`OnboardingTarget`:
   `dev`/`staging`), and `--database-url` (raw string, MCP). Three flag
   names, three vocabularies, two enums. `app` is not even an
   environment name — it is a role alias that resolves to `MACRODB_APP_URL`,
   which is `macrodb_dev` locally and `macrodb_prod` in cloud. That
   context-dependence is invisible at the call site.

2. **Two option-declaration styles.** `onboard` uses
   `Annotated[T, typer.Option("--flag", …)]` with explicit flag names;
   `seed`/`serve`/`bootstrap` use bare `typer.Option(default=…)` and
   rely on auto-generated names.

3. **The destructive-action guard is re-implemented per command.**
   `seed` and `bootstrap fred-us-macro` each hand-roll
   `if reset and not confirm: raise BadParameter("--reset requires --confirm")`.
   `debug-smoke` rejects `--reset` in a *different* place (a `ValueError`
   in `_helpers`, surfaced as exit 2). No shared pattern.

4. **Error → exit-code mapping diverges.** `bootstrap`/`onboard` catch
   `ValueError` → `Exit(2)`; `seed` converts `ValueError` →
   `BadParameter`. Same failure class, two code paths.

5. **Output is bespoke per command** (`database=… run_date=…` vs
   `target: inserted=…` vs `session_id=…`), with no `--json` and no
   shared formatter, so nothing is reliably scriptable.

6. **MCP is split into two console scripts** (`macrodb-mcp`,
   `macrodb-mcp-write`), and `macrodb-mcp-write` is wired to the Typer
   *command function* `mcp.server:write_enabled` rather than the app
   `:main`, inconsistent with `macrodb-mcp = …:main`. MCP servers accept
   only a raw `--database-url`, not the project's target vocabulary.

7. **`serve` defaults to `--reload=True`** (a dev-only footgun) and
   *silently* forces reload off for `--database test`.

8. **`onboard` carries 18 model-override flags** (`--<role>-model` and
   `--<role>-deep-model` for nine roles). They dominate `--help` and are
   unwieldy.

`docs/environments.md` is already the source of truth for "which
database does X target?" and names the four logical databases
`macrodb_dev` / `macrodb_test` / `macrodb_staging` / `macrodb_prod`. It
even documents `macrodb onboard --target dev`. The CLI's `--database app`
vocabulary predates and contradicts that.

## Decision

Adopt one set of CLI conventions across every `macrodb` command, and
restructure the command tree accordingly. This is internal pre-1.0
surface, so the renames below are made as one breaking batch with no
backward-compatible aliases.

### Conventions (apply to every command)

- **One declaration style.** Always
  `Annotated[T, typer.Option("--flag", help=…)]` with an explicit flag
  name. No reliance on auto-generated names.

- **One target vocabulary.** A single `EnvTarget` enum —
  `dev | test | staging` — replaces both `DatabaseTarget` and
  `OnboardingTarget`. It aligns with `docs/environments.md` and ADR 0009.
  `prod` is deliberately absent: the CLI never targets production
  (promotion is an outer workflow). The flag is always `--target`.
  Each command declares the subset it accepts and rejects the rest with
  a uniform error (e.g. `seed` refuses `staging`; `onboard` refuses
  `test`). The `app` value is retired.

- **One raw-URL escape hatch.** `--database-url` survives only on
  `serve mcp`, where an MCP client may need to point a process at an
  arbitrary URL. It overrides `--target` when both are given.

- **One destructive-action pattern.** Drop the `--reset --confirm`
  pair. A destructive command (`--reset`, or any delete path) prompts
  interactively via `typer.confirm` by default and is skippable with a
  single global **`--yes` / `-y`**. One shared helper, one code path.

- **One error path.** A shared decorator maps domain `ValueError` →
  `Exit(2)` with the message on stderr. No per-command divergence
  between `BadParameter` and `Exit`.

- **One output contract.** A shared result-printer renders the existing
  human-readable `key=value` lines by default and a structured object
  under a global **`--json`** flag, so every command is scriptable.

- **Safe defaults.** `serve api` defaults to `--reload` *off*; reload is
  opt-in. No silent behaviour change based on target.

### Command tree

```
macrodb onboard [--target dev|staging] [--resume ID]
                [--model ROLE=NAME ...] [--cost-cap USD]
macrodb seed    [--only ...] [--dry-run] [--reset] [-y]   --target dev|test
macrodb db bootstrap <preset> [--reset] [-y]              --target dev|test
macrodb serve api  [--host] [--port] [--reload]           --target dev|test
macrodb serve mcp  [--write] [--database-url URL]         --target dev|test|staging
```

- `bootstrap` moves under a `db` noun-group (`macrodb db bootstrap …`),
  joining `seed` as a database-population command. Presets
  (`fred-us-macro`, `debug-smoke`) stay as positional/sub-values.
- **MCP folds into `macrodb serve mcp [--write]`**, collapsing the two
  console scripts into one consistent surface and removing the
  `:write_enabled`-vs-`:main` entry-point inconsistency. The
  `macrodb-mcp` / `macrodb-mcp-write` scripts are removed.
- The 18 onboard model flags collapse to a single repeatable
  `--model ROLE=NAME` (and an optional `--deep-model ROLE=NAME`),
  parsed into the existing `RoleOverride` map.

## Consequences

- A learner sees one flag (`--target`), one vocabulary, one
  confirmation idiom, and one output mode across the whole CLI. `--help`
  for `onboard` shrinks from ~20 flags to a handful.
- `docs/environments.md` becomes literally true of the CLI: `--target`
  values are the environment names it already documents.
- New commands inherit the shared helpers (target resolver, confirm
  guard, error decorator, printer) instead of re-deriving them, so the
  surface stays consistent as later phases add commands.
- **Breaking changes**, batched: `--database`→`--target` (+ `app`
  retired in favour of `dev`); `--confirm`→`-y`; the `macrodb-mcp` /
  `macrodb-mcp-write` console scripts replaced by `macrodb serve mcp`;
  the per-role onboard flags replaced by `--model ROLE=NAME`. Any MCP
  client config or script invoking the old names must update. Because
  this is pre-1.0 internal tooling with a single operator, no alias
  shim is provided.
- `EnvTarget` replaces `DatabaseTarget` and `OnboardingTarget`; their
  `database_url_for_*` resolvers consolidate into one
  `database_url_for_target(EnvTarget)` with per-command subset
  validation at the CLI boundary.
- Implementation is deferred. This ADR is the spec; the refactor lands
  as a follow-up once accepted.

## Alternatives considered

- **Unify the flag name only, keep two enums.** Rejected. Renaming
  `--database`→`--target` without unifying the value vocabulary leaves
  the deeper confusion (`app`/`test` vs `dev`/`staging` meaning the same
  axis) in place. The single `EnvTarget` is the actual fix and matches
  `docs/environments.md`.
- **Keep MCP as separate console scripts**, fixing only the
  `:write_enabled` wiring and adding `--target`. Rejected. Two extra
  entry points for what is conceptually "serve a server" perpetuates the
  split; `serve api` / `serve mcp` is the honest grouping. MCP client
  configs are few and operator-owned, so the migration cost is low.
- **Keep `--reset --confirm`.** Rejected. Two flags for one intent,
  re-implemented per command, with a third divergent path in
  `debug-smoke`. An interactive confirm with a `-y` override is the
  standard CLI idiom and removes the per-command boilerplate.
- **Backward-compatible aliases for every renamed flag/script.**
  Rejected. Aliases double the surface this ADR is trying to shrink, for
  a single-operator pre-1.0 tool. A clean break is cheaper than carrying
  the old vocabulary.
- **Add `prod` to `EnvTarget` for completeness.** Rejected. The CLI must
  not be able to target production; promotion is a separate workflow
  (ADR 0009, `docs/environments.md`). Omitting the value enforces that
  at the type level.
- **Implement the refactor now rather than spec-first.** Deferred per
  the project's decision-first cadence: settle the conventions in an ADR,
  then execute against them.
