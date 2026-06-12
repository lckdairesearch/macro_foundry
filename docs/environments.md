# Environments

macrodb operates against four logical databases. This document records the
purpose of each, where it lives, what may touch it, and how onboarding and
promotion flows route between them.

This document is the source of truth for "which database does X target?".
`docs/architecture.md` covers the connection details (driver, pool settings,
role split). `docs/series_onboarding_workflow.md` references this document for
the onboarding target.

## The four databases

| DB | Hosted on | Role | Lifecycle | Onboarding role |
|---|---|---|---|---|
| `macrodb_dev` | Local Docker | Developer playground | Reset whenever the developer wants; no durability guarantees | Used for dry-run onboarding sessions (`macrodb onboard --target dev`) |
| `macrodb_test` | Local Docker | Pytest target | Reset by `conftest.py` fixtures; never durable | Allowed only for local test-environment onboarding runs; never a durable onboarding workflow target |
| `macrodb_staging` | Neon | Durable pre-prod environment | Long-lived; reset only by deliberate ops action | Default target for `macrodb onboard`; where first ingestion runs execute and where onboarding packages land |
| `macrodb_prod` | Neon | Production | Long-lived; mutated only via the separate promotion workflow | The CLI cannot target prod. Promotion is handled by an outer workflow |

## Dev vs staging — the sharpest difference

`macrodb_dev` is yours. You can break it, reset it, ignore it, hand-edit it,
point it at a half-finished migration. It exists to let you iterate. No
process or workflow depends on its state.

`macrodb_staging` is the system's. Its content is the result of approved
onboarding sessions. Its schema is always at HEAD (no half-finished
migrations). It is the snapshot that is about to be promoted to prod. If
staging is broken, the system is in a bad state.

If you ever feel the urge to hand-edit staging, that is a signal that the
onboarding workflow has a gap, not that staging needs to be more flexible.

## Why staging lives on Neon, not local Docker

Staging only earns its name if it mirrors the production environment. The
gaps that staging is meant to close — Neon's scale-to-zero behavior,
connection pooler quirks under realistic latency, JSONB performance at
non-trivial sizes, version drift between local PG 18.4 and Neon's PG 18 —
are exactly the gaps that local Docker cannot reveal. Staging on Docker would
provide false confidence.

Staging on Neon also makes the eventual promotion path a Neon-to-Neon
operation (`pg_dump`/`pg_restore`, Neon branching, or a future replicator)
instead of a Docker-to-Neon cross-environment operation.

Cost is negligible. A second Neon project on the free tier is fine while
usage is sparse; even paid tier is a rounding error against a single-operator
project.

A possible future direction: stand `macrodb_staging` up as a Neon *branch* of
`macrodb_prod`, periodically refreshed, so onboarding sessions run against a
recent copy of real production data. Not built today, but the fact that the
option is available is part of why staging belongs on Neon.

## Why pytest is not a durable onboarding target

`macrodb_test` is the pytest target. Its schema is up-to-date with
migrations, and its data is wiped frequently by test fixtures. Both
properties are incompatible with durable onboarding:

- onboarding sessions persist catalog rows that the operator wants to
  inspect across days, not seconds
- a wipe between fixture invocations would erase a half-approved onboarding
  package without warning

Conflating the two would produce a workflow where reviewers cannot trust
that the rows they reviewed last week still exist. Keeping them separate is
the simpler safety property.

The CLI allows `macrodb onboard --target test` only for local test-environment
onboarding runs and prints a warning when it is used. A test-targeted session
must not be treated as part of the durable onboarding workflow.

## Agent process targeting

A LangGraph onboarding session locks its target at session creation. The
selected target is part of the immutable session metadata in the checkpoint.

Resuming a session reuses its original target. A session that began against
`staging` cannot finish against `dev`. Retargeting requires aborting the
session and starting a new one.

The CLI default is `--target staging`. The other accepted values today are
`dev` and `test`; `test` remains local and non-durable only.

The custom `macrodb-mcp` server is process-agnostic: the same server binary
serves any environment, connected by a different connection string. The
environment a session targets is reflected in the MCP connection string the
agent is launched with, not in the server build.

## Role separation across environments

The two-role model from ADR 0006 (`macrodb_owner` for migrations,
`macrodb_app` for everything else) applies in all four environments. Onboarding
agent traffic and ingestion runtime traffic both connect as `macrodb_app`. The
agent never runs migrations and never connects with owner credentials.

The LangGraph checkpointer in the `langgraph` schema is owned by
`macrodb_owner` (created during initial setup) and read/written by
`macrodb_app`. The checkpointer schema is not entangled with `public` schema
mutations.

## Promotion is out of scope here

This document stops at `staging`. The promotion path from `staging` to `prod`
is governed by an outer workflow not yet specified. The onboarding package
emitted by a successful onboarding session is the input to that future
workflow. See `docs/series_onboarding_workflow.md` for what the package
contains.
