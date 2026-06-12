# Architecture Decision Records

This directory holds the decisions that shape `macro_foundry`. Each ADR is a
short, self-contained record of a decision made: the context, what was decided,
the consequences, and the alternatives that were considered.

ADRs are immutable once accepted. If a decision changes, write a new ADR that
references and supersedes the old one — don't edit the old one.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-uuidv7-server-side-defaults.md) | uuidv7 server-side defaults | Accepted |
| [0002](0002-enum-check-constraint-pattern.md) | Enum / CHECK constraint pattern | Accepted |
| [0003](0003-thin-crud-generator-over-postgrest.md) | Thin in-repo CRUD generator over PostgREST / Supabase / Django / SQLModel | Accepted |
| [0004](0004-psycopg3-async-not-asyncpg.md) | psycopg3 async over asyncpg | Accepted |
| [0005](0005-no-native-pg-enums.md) | No native Postgres ENUM types | Accepted |
| [0006](0006-two-role-architecture.md) | Two-role database architecture | Accepted |
| [0007](0007-subnational-regions-as-country-scoped-groupings.md) | Subnational regions as country-scoped grouping geographies | Accepted |
| [0008](0008-foreign-key-delete-policy.md) | Foreign key delete policy | Accepted |
| [0009](0009-physical-database-naming-by-environment.md) | Physical database naming by environment | Accepted |
| [0010](0010-request-level-ingestion-and-series-hierarchy.md) | Request-level ingestion and canonical series hierarchy | Accepted |
| [0011](0011-gated-onboarding-graph.md) | Gated onboarding graph implemented as a chat-session LangGraph agent | Accepted |
| [0012](0012-selector-registry-ingestion-runtime.md) | Selector-registry ingestion runtime | Accepted |
| [0013](0013-metadata-standardisation.md) | Metadata standardisation in the gated onboarding workflow | Accepted |
| [0014](0014-enum-gap-escalation.md) | Enum-gap escalation in the gated onboarding workflow | Accepted |
| [0015](0015-reviewer-role-consolidation.md) | Reviewer role consolidation in the gated onboarding workflow | Accepted (partially amends ADR 0011) |
| [0016](0016-credential-gap-escalation.md) | Credential-gap escalation in the gated onboarding workflow | Accepted |
| [0017](0017-cli-interface-standardisation.md) | `macrodb` CLI interface standardisation | Accepted |
| [0018](0018-scoping-three-node-split.md) | Scoping subgraph splits clarify, verify, and brief authoring into separate nodes | Accepted |
| [0019](0019-check-db-node-for-onboarding.md) | `check_db` node for catalog-duplicate detection in onboarding | Proposed |
| [0020](0020-catalog-embeddings-for-semantic-search.md) | Catalog embeddings for semantic search | Proposed |

## Format

When you write a new ADR, follow this skeleton:

```markdown
# ADR NNNN — Short title

**Status:** Proposed | Accepted | Superseded by [NNNN]

**Date:** YYYY-MM-DD

## Context

What problem is this decision addressing? What forces are in play?

## Decision

What we decided to do. Specific. Cite code patterns if useful.

## Consequences

What this enables. What it costs. What follow-on work it implies.

## Alternatives considered

Each viable alternative with a short rejection rationale.
```

Keep ADRs short. Aim for 1-2 pages. They are reference material, not essays.
