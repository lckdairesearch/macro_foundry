# Progress Tracker

This file is the living record of what's been done. Update it when a phase
completes, when something deviates from the build plan, or when a handoff
between sessions happens.

Format per entry: `[YYYY-MM-DD] Phase N — Status. Notes.`

Most recent at the top.

---

## Log

### [2026-06-20] Issue 78 — drop the V7 conceptual spine (ADR 0025 §1)

Destructive half of the V8 collapse: removed `concepts`, `indicators`,
`indicator_variants`, `tags`, and `concept_tags` end-to-end. A drop-and-rebootstrap,
not a data migration — the catalog is regenerable. Blocked-by #77 (V8 `db_er.txt`
canonical) is closed.

Migration `0017_drop_v7_conceptual_spine` (down_revision `0016`, single head):
- `upgrade` drops the 5 tables (FK-safe order) and tightens both governance CHECKs;
- `downgrade` re-admits the dropped vocabulary and recreates all 5 tables at their
  head shape (embedding columns + HNSW indexes on `concepts`/`indicators`, the
  `tags.code` key, the renamed indicator constraints) so the round-trip is clean;
- assumes the governance audit tables carry none of the dropped vocabulary
  (guaranteed under ADR 0025's reset/reseed/rebootstrap workflow) — no silent
  row deletion.

Governance enums: dropped `TargetType.{CONCEPTS,INDICATORS,TAGS,INDICATOR_VARIANTS}`
and `ProposalType.{ADD_INDICATOR,ADD_CONCEPT}` (the latter beyond #78's strict
`target_type` scope, per operator decision). The named CHECKs follow the ADR-0014
widen→tighten pattern.

App surface removed: SQLAlchemy models (`Concept`, `Indicator`, `IndicatorVariant`,
`Tag`, `ConceptTag`) + the `Series.indicator_variant` / `Geography.indicators`
relationships; Pydantic schemas (`Concept*`, `Tag*`, `Indicator*`,
`IndicatorVariant*`); 5 CRUD routers + their registration; 2 SQLAdmin views +
the concept/indicator admin stats; `series` detail tag-flattening. The
`series-hierarchy-edges` route's same-concept guard (which rode the indicator
chain) was reduced to distinct-existing-endpoint validation — flag: re-introduce a
same-category guard once `series.category_id` lands.

Callers neutralized (full rewrite deferred to the rebootstrap slice): the series
embedding recipe drops indicator/concept context; `register_concept`/
`register_indicator` removed (only `register_series` remains); `embeddings backfill`
and the MCP read tools are series-only (concept/indicator lookup, drill-down, and
search retired); `propose_create_series` + the MCP apply-path spine branches and
both bootstrap entrypoints (`fred_us_macro`, `debug_smoke`) are stubbed to raise
`NotImplementedError` (curated specs preserved in git history); tag seed removed.

Tests: deleted `test_fred_bootstrap` / `test_debug_bootstrap`; rewrote the
embedding/registration/MCP-read suites to series-only; trimmed seed/schema/
constraint/admin/series-route coverage; added `tests/shared/test_drop_v7_spine.py`
(tables absent at head + CHECK rejects the dropped values) and reframed the #69
governance enum test (upgrades to 0016, then asserts the V7 vocabulary is gone).

Verification: `uv run ruff check src/macro_foundry` clean; full package imports and
the FastAPI app boots (86 routes, no dropped tables mapped); changed `-m no_db`
tests green (13 passed). **Operator to run with Docker up:** the migration
round-trip (`tests/shared/test_migrations.py`, `tests/shared/test_drop_v7_spine.py`,
`tests/shared/test_governance_enum_rename.py`) and the DB-backed `tests/macrodb`
suite — the local test DB was not reachable this session.

Follow-ups (out of #78 scope): CONTEXT.md glossary + `architecture.md` natural-key
prose still describe the V7 spine (separate doc sweep); the V8 rebootstrap slice
rebuilds bootstrap/registration/MCP-write against the `categories` tree; the
pre-existing `macro_foundry.agent` collection failures (ADR 0023 retirement) are
unrelated and untouched.

### [2026-06-13] ADR 0023 — retire the legacy `agent` package; correct ADR 0021's embeddings claim

Wrote `docs/adr/0023-retire-legacy-agent-package.md` (Accepted, amends ADR 0021)
and indexed it. The ADR:

- declares `src/macro_foundry/depreciated_omit_this_agent` (formerly
  `src/macro_foundry/agent`) **retired** — excluded from all sweeps, slated for
  deletion — and names `src/macro_foundry/onboarding_agent` the single canonical
  agent under construction;
- sets a **precedence rule**: where the retired package's code/prompts/docs
  contradict the current schema, vocabulary, an ADR, or the `onboarding_agent`
  design, the retired package is authoritatively wrong and is deprioritised;
- keeps ADRs 0011, 0013–0016, 0018 as historical records — their decisions stand,
  their wiring into the retired package is superseded;
- **corrects ADR 0021** (line 82–83): the in-place rename preserves rows but
  **not embeddings**. The indicator recipe-label changes drift the embedding
  input, so a re-embed is required; a **full re-embed of all catalog embeddings**
  (`concepts`, `indicators`, `series`) is acceptable rather than a scoped backfill.

Also closed the last `family`-vocab doc-sweep gaps (#71 residue): ADR 0019 line
112 `find_sibling_series(indicator_id)`; ADR 0022 lines 27/35/133
`indicator_variants → indicators` / `indicator_variant → indicator`.

Note: the prior entry below said `src/macro_foundry/agent` was "deleted" — it was
in fact **renamed** to `depreciated_omit_this_agent` and remains on disk (still
importable-named but contradictory); treat per ADR 0023's precedence rule.

### [2026-06-13] Rename follow-up — agent wire vocab + embedding labels finish the indicator sweep

Sanity-check cleanup after #68–#71, closing the last `family` vocab that the #68
"out of scope" note had deferred, plus the stale `family` labels the schema
rename left inside the embedding recipes. Confirmed `src/macro_foundry/agent` is
gone (deleted, not just retired) and the heavy `family`-vocab test files import
it — they fail at collection and will be removed with the agent, so they were
left untouched. Only the live MCP surface, the onboarding-agent prompts, and the
embedding recipes needed changing.

Agent wire vocab (item 5):

- `FindSiblingSeriesArgs.family_id` → `indicator_id` (`mcp/read_tools.py` +
  `mcp/server.py` `find_sibling_series` arg)
- write-tool apply path (`mcp/write_tools.py`): `_resolve_family` →
  `_resolve_indicator`; consumed `proposed_data` keys
  `family_id`/`family_code`/`variant`/`is_primary` →
  `indicator_id`/`indicator_code`/`label`/`is_default`; `propose_create_series`
  return key `family_id` → `indicator_id`
- onboarding-agent `check_db` verdict field `similar_series[].family_id` →
  `indicator_id` (`onboarding_agent/prompts.py`)
- `tests/macrodb/test_mcp_read_tools.py` updated to the new arg

Embedding-recipe labels (item 6) — **requires a backfill**:

- `compose_indicator_embedding_input`: `Type: SeriesFamily` → `Type: Indicator`
- `compose_series_embedding_input`: `Family: …` → `Indicator: …`
- Both drift the stored `embedding_input_hash`, so an **indicators + series**
  re-embed is required: `uv run macrodb embeddings backfill`. This is the
  sanctioned `compose_indicator` / `compose_series` label change in ADR 0020's
  recipe-change scope table; it supersedes the #68 "pure rename, no backfill"
  note below. ADR 0020 recipe examples and the two literal-text embed tests
  (`test_embeddings_service.py`, `test_registration_services.py`) updated to
  match.

Deliberately left (broken now, pending rewrite under the onboarding agent, all on
the deleted `macro_foundry.agent` import): `depreciated_omit_this_agent/`,
`cli/onboard.py`, and `propose_create_series` Path A's `draft.family*` reads.

Verification: `uv run ruff check` clean; module imports clean;
`uv run pytest tests/macrodb -q -m no_db` green for the touched files. DB-backed
embedding tests and the actual `embeddings backfill` need a live `macrodb_test`
run by the operator.

### [2026-06-13] Issue 71 — documentation sweep: series_family → indicator (ADR 0021)

Terminology sweep across all prose docs to match the schema rename completed in
issues #68–#70. No schema or code changes; docs only.

Files updated: `CONTEXT.md` (glossary), `CLAUDE.md`, `AGENTS.md`,
`docs/adr/0008`, `docs/adr/0013`, `docs/series_catalog_governance.md`,
`docs/skills/skill-concept-vs-family-vs-variant.md`,
`docs/skills/skill-metadata-standardisation.md`, `docs/build_plan.md`,
`docs/code_standards.md`, `docs/series_onboarding_workflow.md`.

Key changes:
- Glossary heading `### Series family` → `### Indicator`; `### Variant` →
  `### Indicator variant`; `is_default` documented as the default-variant marker
- `series_family_members` → `indicator_variants`, `series_family` →
  `indicator`/`indicators`, `variant` column → `label`, `is_primary` →
  `is_default` throughout prose
- Seed exemplar fields in `skill-metadata-standardisation.md` updated to new
  table/column names

---

### [2026-06-13] Issue 69 — governance stored-enum values follow the indicator rename

Brought the governance audit vocabulary in line with the `series_family →
indicator` table rename (#68). These values are *persisted* under named CHECK
constraints (no native PG enums), so this is a stored-data change on a different
table than #68, with its own data migration.

Value renames:

- `change_proposal_items.target_type` `series_families → indicators`
- `change_proposal_items.target_type` `series_family_members → indicator_variants`
- `change_proposals.proposal_type` `add_family → add_indicator`

Layers touched:

- `enums/governance.py` — member identifiers + string values renamed
  (`TargetType.INDICATORS`, `TargetType.INDICATOR_VARIANTS`,
  `ProposalType.ADD_INDICATOR`); member references updated in
  `mcp/write_tools.py` and `tests/macrodb/test_write_mcp.py`
- Alembic `0014_rename_governance_indicator_values.py` (down_revision `0013`,
  single head) follows the ADR-0014 enum-gap pattern: widen each named CHECK to
  the old∪new union → `UPDATE` existing rows old→new → tighten CHECK to the new
  set. No VARCHAR widening needed — renamed values are no longer than the
  existing maxima (`geography_memberships` / `add_provider_series`). Downgrade
  reverses symmetrically.
- V3 source `docs/schema/db_er.txt` proposal_type enum comment updated to
  `add_indicator` (target_type line already carried `indicators` /
  `indicator_variants` from #68).

Verification:

- `uv run pytest tests/shared/test_governance_enum_rename.py -q` green — new
  file covering the enum vocabulary and a migration roundtrip that inserts rows
  under the old vocabulary at `0013`, upgrades, and asserts they are renamed and
  the tightened CHECK rejects the retired values.
- `uv run pytest tests/macrodb/test_write_mcp.py tests/shared/test_migrations.py tests/test_migrations.py tests/macrodb/test_apply_catalog.py tests/macrodb/test_executor_nodes.py -q` green.
- `uv run pytest tests/macrodb -q -m no_db` → `238 passed, 1 failed`; the single
  failure is the pre-existing `test_onboarding_scope`
  `FakeModel.with_structured_output(strict=…)` signature mismatch noted in the
  #68 entry, on a file this slice never touched.
- `uv run macrodb db migrate --target {test,dev}` both at `0014`;
  `uv run alembic heads` reports a single head `0014`.
- `uv run ruff check` clean across all changed files.

### [2026-06-13] Issues 72–75 — concept-grained topical tags (ADR 0022)

Regrained the topical tag taxonomy from `series` to `concept` and gave `tags`
a canonical `code` key, per ADR 0022. The `series_tags` junction was inert
(nothing ever constructed a row), so this is a clean drop-and-recreate with no
data migration.

Schema / model changes:

- `tags` gains a `code` (UPPERCASE canonical key, `uq_tags_code`); `name`
  becomes free display text. Modeled like `concepts` — no `code_standard`.
- `series_tags (series_id, tag_id)` dropped; `concept_tags (concept_id, tag_id)`
  created with composite PK and `ON DELETE CASCADE` FKs.
- `SeriesTag → ConceptTag`; `Series.series_tags` removed,
  `Concept.concept_tags` added; schemas, admin view, and CRUD router renamed
  (`/series-tags → /concept-tags`).
- Series detail API now derives tags transitively via
  `indicator_variant → indicator → concept → concept_tags → tag`
  (deeper `selectinload`, no lazy loading); empty when a series has no variant.

Taxonomy: the 7 legacy subject names replaced by the 10-category topical set
(ADR 0022 §3), seeded as `(code, name)` tuples and upserted on `code`:
`PRICES`, `MONETARY_BANKING`, `POPULATION_LABOR`,
`PRODUCTION_BUSINESS_ACTIVITY`, `RETAIL_CONSUMPTION`, `NATIONAL_ACCOUNTS`,
`GOVERNMENT_FISCAL`, `INTERNATIONAL`, `FINANCIAL_INDICATORS`, `OTHER`.

Migrations: `0015_tags_code` (add `code`, swap unique constraint, drop seed) and
`0016_concept_tags` (drop `series_tags`, create `concept_tags`), chained after
`0014_rename_governance_indicator_values` (#69) to keep one linear Alembic head.

Governance: codified the UPPERCASE / SCREAMING_SNAKE `code` casing rule in
`CONTEXT.md` (convention-only, not validator/CHECK-enforced — ADR 0022 §4);
`architecture.md` natural-key reference moved `tags.name → tags.code`;
`code_standards.md` composite-PK junction examples updated to `concept_tags` /
`indicator_variants`.

Also synced `db_er.txt` to the V7 baseline (embeddings + governance audit
vocabulary) the branch had not yet picked up, then applied the tag regrain on
top, so the canonical schema is whole rather than V6-with-tags.

Still owed (follow-on, not this slice): populating `concept_tags` — a curated
`concept_code → [tag_code]` seed — which the concept grain makes tractable.

### [2026-06-13] Issue 68 — core rename `series_family → indicator` (ADR 0021)

Atomic rename of the catalog's middle rung across every layer that shares
Python imports or the Alembic chain, per ADR 0021 (#67). No backwards-compat
shims; data carried forward in place.

Rename applied:

- tables `series_families → indicators`, `series_family_members → indicator_variants`
- columns `family_id → indicator_id`, `variant → label`, `is_primary → is_default`
- classes `SeriesFamily → Indicator`, `SeriesFamilyMember → IndicatorVariant`
  (and the Pydantic schema classes + REST `IndicatorVariantCreate` body fields)
- relationships/attrs `Concept/Geography.series_families → .indicators`,
  `Indicator.members → .variants`, `IndicatorVariant.family → .indicator`,
  `Series.family_member → .indicator_variant`
- service API `register_family → register_indicator`,
  `compose_family_embedding_input → compose_indicator_embedding_input`
- named constraints/indexes renamed to match: `uq_indicators_code`,
  `uq_indicator_variants_series_id`, both pkeys, the two indicator FKs, the two
  indicator_variant FKs, and `ix_indicators_embedding_hnsw`
- SQLAdmin display names + landing card/identity, CLI reset-summary fields, the
  `embeddings backfill` summary key

Alembic: `0013_rename_series_family_to_indicator.py` uses in-place
`ALTER TABLE … RENAME` / `RENAME COLUMN` / `RENAME CONSTRAINT` / `ALTER INDEX …
RENAME` (no drop+recreate); PG18 named NOT NULL constraints left untouched
(invisible to ORM/autogenerate; renaming them risks Neon portability).

**Migration number.** This slice landed first and owns `0013_rename_series_family_to_indicator`
(down_revision `0012`). A parallel slice (#72) had provisionally claimed `0013`
for a tags migration but it was never committed; whoever merges after this must
rebase onto the new head (`0013` = this rename) and number their migration `0014`.

Out of scope (handled in later slices, deliberately left): governance stored-enum
values `series_families`/`series_family_members`/`add_family` (#69); MCP tool
*names* `lookup_family`/`search_series_families` + `FindSiblingSeriesArgs.family_id`
arg and REST URL prefixes `/series-families`, `/series-family-members` (#70);
the retired `src/macro_foundry/agent` dir (its `DraftProposal.family` /
`proposed_data` JSON keys are the unchanged producer contract the MCP write tool
reads); non-schema docs (#71).

Embeddings: at this slice, a **pure rename** with no semantic change — the
`Type: SeriesFamily` and `Family:` labels in the composed embedding input were
intentionally preserved (only code symbols moved), so no `embedding_input_hash`
drift. **Superseded 2026-06-13** (see the top "Rename follow-up" entry): those
labels were later updated to `Indicator`, which now requires an indicators +
series `embeddings backfill`.

Verification:

- `uv run pytest tests/test_migrations.py -q` and
  `uv run pytest tests/shared/test_migrations.py -q` both green (upgrade/downgrade
  roundtrip locks model⇆DB agreement on the renamed tables/columns/index). Also
  fixed a pre-existing staleness in root `tests/test_migrations.py` (its
  `EXPECTED_TABLES` was missing `series_hierarchy_edges`, `ingestion_feed_members`,
  `ingestion_run_log_members`).
- `uv run pytest tests/macrodb tests/shared -q` → `379 passed, 2 failed`; both
  failures pre-existing and unrelated (the known-flaky
  `test_concurrency_advisory_warns_when_another_session_exists`, passes in
  isolation; and `test_onboarding_scope` `FakeModel.with_structured_output(strict=…)`
  signature mismatch on files this slice never touched).
- Root `tests/test_e2e.py`, `tests/test_migrations.py` green individually.
  `tests/test_constraints.py::test_series_source_external_code_is_unique_within_catalog`
  fails but is pre-existing and unrelated: migration `0004` dropped
  `uq_series_sources_catalog_external_code`, so the constraint correctly does not
  exist at head — the stale root test was never run in standard CI.
- `uv run ruff check` clean across all changed files.

### [2026-06-12] Issue 61 — added pure embedding service module

Added `src/macro_foundry/services/embeddings.py` as the ADR 0020 text-composition
and OpenAI client layer used by later registration/search slices.

- locked constants: `EMBEDDING_MODEL = "text-embedding-3-small"` and
  `EMBEDDING_DIMENSIONS = 1536`
- locked humanization maps for `Frequency`, `UnitKind`, `Measure`, and
  `SeasonalAdjustment`
- pure recipe functions:
  `compose_concept_embedding_input`,
  `compose_family_embedding_input`,
  `compose_series_embedding_input`
- `hash_embedding_input(text)` as SHA-256 hex prefix (16 chars)
- async `embed_text(text)` reading `OPENAI_API_KEY` through
  `settings.llm.openai_api_key`, retrying exactly once on transient
  connection/rate-limit/5xx failures, and failing immediately on auth or
  insufficient-quota errors

Added `tests/macrodb/test_embeddings_service.py` covering the locked recipe
strings, omit-empty rule, exact humanization maps, hash determinism, and the
mockable `embed_text` retry/error behavior.

Verification:

- `uv run pytest tests/macrodb/test_embeddings_service.py -q -m no_db` exited 0
  with `10 passed`
- `uv run ruff check src/macro_foundry/services/embeddings.py tests/macrodb/test_embeddings_service.py`
  exited 0
- live OpenAI probe through `embed_text("headline inflation rate, monthly, United States")`
  returned a `list[float]` of length `1536`

### [2026-06-12] Issue 60 — catalog embedding schema migration and local pgvector support

Landed the schema foundation from ADR 0020:

- Alembic revision `0012_catalog_embedding_columns.py` adds
  `embedding vector(1536)`, `embedding_model text`, and
  `embedding_input_hash text` to `concepts`, `series_families`, and
  `series`, plus one HNSW cosine index per table.
- Downgrade drops the three column sets and the HNSW indexes while
  leaving the `vector` extension installed.
- `tests/shared/test_migrations.py` now covers both directions:
  `head` exposes the columns/indexes and supports a real vector
  insert/cosine query on `concepts`; downgrade to `0011` removes the
  embedding schema but keeps the extension in place before re-upgrading
  to `head`.

Local-infra note: the issue looked migration-only, but local Docker did
not actually provide pgvector. To make the acceptance criteria real on a
fresh local environment, `docker-compose.yml` now uses the official
`pgvector/pgvector:0.8.2-pg18` image and
`docker/postgres/init/01_roles.sql` enables `vector` in both
`macrodb_dev` and `macrodb_test` during first boot. This keeps Alembic
running as `macrodb_owner` while avoiding a local-only privilege failure
on `CREATE EXTENSION`.

Verification:

- `.venv/bin/pytest tests/shared/test_migrations.py -q` exited 0 with
  `3 passed`.
- `.venv/bin/ruff check alembic/versions/0012_catalog_embedding_columns.py tests/shared/test_migrations.py`
  exited 0.
- `.venv/bin/macrodb db migrate --target test` exited 0 with
  `before=0012 after=0012`.

### [2026-06-12] CLI — added `macrodb db migrate --target {dev|test}`

Plugged the ergonomic gap surfaced by the `series.alt_name` rollout:
`uv run alembic upgrade head` only ever touched `MACRODB_OWNER_URL`
(= `macrodb_dev`), so the test database silently drifted behind the
model whenever a migration landed locally, and `macrodb serve api
--target test` would 500 on any table the migration added a column to.

New surface:

```
macrodb db migrate --target {dev|test} [--revision REV] [--downgrade] [--json]
```

`--target` defaults to `dev`, matching the rest of the CLI. The
command resolves the owner-role URL for the selected target via a new
`owner_url_for_env_target` helper (reuses the database-name swap
pattern from `tests/conftest.py:_owner_test_url`), then runs Alembic
programmatically. Output is key=value (or JSON) and includes
before/after revisions so a no-op upgrade is obvious from a glance.

`alembic/env.py` now respects a pre-set `sqlalchemy.url` on the
Alembic Config and only falls back to `settings.db.owner_url` when
nothing is set, so terminal `uv run alembic upgrade head` continues to
work unchanged.

Verification:

- `uv run macrodb db migrate --target dev` → `before=0011 after=0011`
  (no-op, dev already at head).
- `uv run macrodb db migrate --target test --downgrade --revision 0010` →
  `before=0011 after=0010`.
- `uv run macrodb db migrate --target test --json` →
  `{"target":"test","direction":"upgrade","revision":"head","before":"0010","after":"0011"}`.
- Direct SQL probe against both URLs confirms `macrodb_dev` and
  `macrodb_test` are distinct physical databases and both carry the
  `series.alt_name` column.
- `uv run ruff check` clean across all touched files.

### [2026-06-12] Series — added `alt_name` column and brought FRED bootstrap prose to skill

Added `alt_name text[]` (nullable) to `series`, mirroring the existing
column on `geographies` and `providers`. Curated, provider-agnostic
search aid; distinct from `series_sources.external_name` (per-provider,
for audit/reconciliation). Surfaces updated end-to-end: V3 schema source
(`docs/schema/db_er.txt`), SQLAlchemy `Series` model, Alembic migration
`0011_series_alt_name.py`, Pydantic `SeriesBase`/`SeriesUpdate`,
SQLAdmin `SeriesAdmin.form_columns`, `DraftSeriesOutput` (so the
onboarding drafter can populate it), and the MCP `apply_catalog` write
path. Mutation matrix in ADR 0013 and skill-metadata-standardisation
extended with the new row (agent-mutable, same tier as `series.name`).

Audited `bootstrap/fred_us_macro.py` against
`docs/skills/skill-metadata-standardisation.md` and fixed three hard-rule
violations across all four raw + four derived FRED specs:

1. Geography-prefix rule — renamed `series_name` and
   `derived_series_name` from `"United States ..."` to `"USA – ..."`
   form (en-dash U+2013), matching skill exemplars 1–5.
2. Runtime-implementation detail rule — rewrote `series_description`
   to drop `"imported from FRED ticker GDP/CPIAUCNS/..."` leakage. The
   FRED tickers stay where they belong, in
   `series_sources.external_code`.
3. Structural-disclosure rule — descriptions now spell out SA vs NSA,
   SAAR, real vs nominal, base year, and U.S. city average scope in
   prose rather than letting them hide in the row's structural columns.

Each spec now also carries a curated `series_alt_name` /
`derived_series_alt_name` tuple including the publisher's full title
(e.g. `"Consumer Price Index for All Urban Consumers: All Items in U.S.
City Average"`) and common informal aliases (`"Headline CPI"`,
`"CPI-U All Items"`, etc.). FRED's runtime `metadata.title` continues
to flow only into `series_sources.external_name` — `series.alt_name`
stays curated, single-writer.

`series_family.name` and `series_family.description` are propose-only
in the mutation matrix and were left alone in this pass; flagged in
the audit for a separate operator-driven sweep.

Verification:

- Manual review of all eight rewritten name/description pairs against
  exemplars 1–5 of `skill-metadata-standardisation.md`.
- No code or test runs yet — recommend running
  `uv run pytest tests/macrodb/ -q -m no_db` plus
  `uv run ruff check src/macro_foundry tests` and applying migration
  `0011` on dev as `macrodb_owner` before merging.

### [2026-06-12] Issue 66 — routed MCP approval-time catalog writes through registration helpers

Refactored the MCP write-tool approval path in
`src/macro_foundry/mcp/write_tools.py` so approved catalog-row inserts for
`concepts`, `series_families`, and `series` materialize through
`register_concept`, `register_family`, and `register_series` instead of
direct ORM construction.

`apply_approved_proposal(...)` now:

- loads proposal items explicitly and applies them in dependency order
  (`concept` → `series_family` → `series` → `series_family_member`);
- resolves foreign keys by either `*_id` or `*_code` in
  `proposed_data`, so same-proposal inserts can refer to earlier rows by
  code;
- creates `series_family_members` after the series row exists and then
  calls `ensure_series_embedding_current(...)` so the stored
  `embedding_input_hash` already reflects live family/concept context;
- wraps the entire approval-time materialization step in a savepoint so
  an embedding failure rolls back all partial writes and leaves the
  proposal in `approved` status.

`src/macro_foundry/services/registration.py` also now reloads series with
`populate_existing=True` inside `ensure_series_embedding_current(...)` so
same-session refreshes do not reuse a stale `Series` identity that still
has `family_member=None`.

Test updates in `tests/macrodb/test_write_mcp.py`:

- mocked `macro_foundry.services.registration.embed_text` for the full
  write-tool suite;
- asserted the existing `apply_catalog` integration path writes embedded
  `Concept`, `SeriesFamily`, and `Series` rows;
- added approval-path coverage for embedded `concept`, `series_family`,
  and `series` materialization;
- added a `series_family_member` approval case that proves the series
  embedding hash is current after family attachment;
- added a rollback case where the second embed call fails and verified no
  partial catalog rows persist and the proposal remains `approved`.

Verification:

- `uv run pytest tests/macrodb/test_write_mcp.py tests/macrodb/test_registration_services.py tests/macrodb/test_fred_bootstrap.py tests/macrodb/test_debug_bootstrap.py tests/macrodb/test_mcp_read_tools.py -q`
  exited 0 with `39 passed`.
- `uv run ruff check src/macro_foundry/mcp/write_tools.py src/macro_foundry/services/registration.py tests/macrodb/test_write_mcp.py`
  exited 0.
- `rg -nP "(?<![A-Za-z])(Concept|SeriesFamily|Series)\(" src/macro_foundry/mcp/write_tools.py`
  returned no matches.

### [2026-06-12] Issue 65 — routed bootstrap catalog writes through registration helpers

Refactored the embedded catalog creation paths in the bootstrap layer to
use the ADR 0020 registration service instead of direct ORM
construction:

- `src/macro_foundry/bootstrap/fred_us_macro.py`
- `src/macro_foundry/bootstrap/debug_smoke.py`

For FRED bootstrap, the create branches of `_upsert_concept`,
`_upsert_series_family`, and `_upsert_series` now call
`register_concept`, `register_family`, and `register_series`
respectively. After the family membership row is created, bootstrap now
calls `ensure_series_embedding_current(...)` so a newly created series
is immediately re-embedded with family/concept context and the live
compose/hash predicate is already true without running
`macrodb embeddings backfill`.

`debug_smoke` now follows the same pattern for `Concept`,
`SeriesFamily`, and `Series` creation, and likewise refreshes each
series embedding after the family-member link exists.

Test updates:

- `tests/macrodb/test_fred_bootstrap.py` now mocks
  `macro_foundry.services.registration.embed_text`, asserts all created
  `concepts`, `series_families`, and `series` rows have populated
  embedding columns, and verifies the composed-hash predicate is already
  current after bootstrap.
- `tests/macrodb/test_debug_bootstrap.py` now mocks the registration
  embedding call and asserts the debug bootstrap's embedded catalog rows
  are populated.
- `tests/macrodb/test_mcp_read_tools.py` now mocks the registration
  embedding call so its bootstrap-backed semantic-search tests remain
  hermetic.
- `tests/macrodb/test_registration_services.py` now cleans up the
  committed concept in the transaction-boundary test so later files do
  not observe leaked catalog state.

Verification:

- `uv run pytest tests/macrodb/test_registration_services.py tests/macrodb/test_fred_bootstrap.py tests/macrodb/test_debug_bootstrap.py tests/macrodb/test_mcp_read_tools.py -q`
  exited 0 with `26 passed`.
- `uv run ruff check src/macro_foundry/bootstrap/fred_us_macro.py src/macro_foundry/bootstrap/debug_smoke.py src/macro_foundry/services/registration.py src/macro_foundry/services/__init__.py tests/macrodb/test_registration_services.py tests/macrodb/test_fred_bootstrap.py tests/macrodb/test_debug_bootstrap.py tests/macrodb/test_mcp_read_tools.py`
  exited 0.
- `rg -nP "(?<![A-Za-z])(Concept|SeriesFamily|Series)\(" src/macro_foundry/bootstrap/fred_us_macro.py src/macro_foundry/bootstrap/debug_smoke.py`
  returned no matches.

### [2026-06-12] Issue 64 — added embed-on-write registration helpers

Implemented the ADR 0020 registration chokepoint in
`src/macro_foundry/services/registration.py`:

- `register_concept(session, payload)`
- `register_family(session, payload)`
- `register_series(session, payload)`

Each helper now composes the row's embedding input through the existing
`services.embeddings.compose_*_embedding_input` functions, calls
`embed_text`, stores `embedding`, `embedding_model`, and
`embedding_input_hash`, flushes the row, and returns it without
committing. A session-scoped async lock serializes ORM mutation so
same-session concurrent registration calls do not corrupt one another.

Scope note: this issue landed only the helpers and their tests. No
bootstrap, MCP write-tool, or other caller refactors were included in
this slice.

Test coverage added in `tests/macrodb/test_registration_services.py`
for:

- populated embedding fields on returned `Concept`, `SeriesFamily`, and
  `Series` rows;
- parent-context composition for family registration;
- caller-owned transaction boundaries (helper does not commit);
- failed embeddings leaving no pending ORM object and no persisted row
  after caller rollback;
- basic same-session concurrent-call safety.

Verification:

- `uv run pytest tests/macrodb/test_registration_services.py tests/macrodb/test_embeddings_backfill.py -q`
  exited 0 with `11 passed`.
- `uv run ruff check src/macro_foundry/services/registration.py src/macro_foundry/services/__init__.py tests/macrodb/test_registration_services.py`
  exited 0.

### [2026-06-12] Issue 63 — added MCP semantic-search read tools

Implemented the ADR 0020 read surface on `macrodb-mcp`:

- `search_concepts(query, limit)` returning `ConceptSearchHit`
  wrapper rows.
- `search_series_families(query, limit)` returning
  `SeriesFamilySearchHit` wrapper rows with family members hydrated via
  `SeriesFamilyReadDetail`.
- `search_series(query, limit)` returning `SeriesSearchHit` wrapper
  rows.

All three tools now embed the natural-language query via
`services.embeddings.embed_text`, rank only rows with non-null
embeddings using pgvector cosine distance (`1 - (embedding <=> query)`
clamped into `[0, 1]`), hydrate through the existing `*Read` schemas,
and are registered on the read-only MCP server via
`READ_ONLY_TOOL_NAMES` and `_register_read_tools`.

Test coverage added for:

- ranked `search_concepts`, `search_series_families`, and
  `search_series` results with wrapper payloads and bounded similarity
  scores;
- exclusion of rows where `embedding IS NULL`;
- empty-catalog behavior (`[]`);
- the two ADR 0020/FRED probe queries:
  `headline inflation monthly United States` →
  `US_CPI_HEADLINE_M_NSA` top hit, and
  `real GDP growth quarterly US` → `US_GDP_REAL_Q_SAAR` top hit;
- MCP read-only server tool registration including the three new tool
  names.

Verification:

- `uv run pytest tests/macrodb/test_mcp_read_tools.py tests/macrodb/test_mcp_server.py -q`
  exited 0 with `17 passed`.
- `uv run ruff check src/macro_foundry/mcp/read_tools.py src/macro_foundry/mcp/server.py src/macro_foundry/schemas/concept.py src/macro_foundry/schemas/series.py src/macro_foundry/schemas/__init__.py tests/macrodb/test_mcp_read_tools.py tests/macrodb/test_mcp_server.py`
  exited 0.

### [2026-06-12] Issue 62 — added `macrodb embeddings backfill` CLI

Landed the ADR 0020 repair path as `macrodb embeddings backfill --target {dev|staging}`.
The command rejects `test`, fails fast when `OPENAI_API_KEY` is absent, scans
`concepts`, `series_families`, and `series` for stale rows using the locked
predicate (`embedding` present, current `embedding_model`, matching
`embedding_input_hash`), and re-embeds stale rows in batches of 50 using a
single OpenAI embeddings call per batch. Added the embedding service module
locally as required groundwork because the branch was missing the closed issue
61 implementation, plus the `0012` Alembic migration and ORM columns needed for
the command to run against real databases.

One-time dev backfill note:

- `uv run macrodb db migrate --target dev` upgraded `macrodb_dev` from `0011`
  to `0012`.
- `uv run macrodb embeddings backfill --target dev` completed successfully on
  2026-06-12 and was a no-op: `concepts: 0 stale`, `series_families: 0 stale`,
  `series: 0 stale`.

Verification:

- `uv run pytest tests/macrodb/test_embeddings_backfill.py -q` exited 0 with
  `5 passed`.
- `uv run ruff check src/macro_foundry/cli/embeddings.py src/macro_foundry/cli/_app.py src/macro_foundry/cli/__init__.py src/macro_foundry/models/concept.py src/macro_foundry/models/series.py src/macro_foundry/models/_vector.py src/macro_foundry/services/__init__.py src/macro_foundry/services/embeddings.py tests/macrodb/test_embeddings_backfill.py alembic/versions/0012_catalog_embedding_columns.py`
  exited 0.
- `uv run macrodb db migrate --target test` reported `before=0012 after=0012`.
- `uv run macrodb embeddings backfill --target dev` reported `0 stale` for all
  three embedded tables; rerunnable no-op confirmed on the live command path.

### [2026-06-12] Onboarding — designed `check_db` node for catalog-duplicate detection and embeddings

Two Proposed ADRs and one prompt landed as the design anchor for the
next onboarding-graph node, slotted between brief authoring and
proposal drafting.

- ADR 0019 (`docs/adr/0019-check-db-node-for-onboarding.md`) — read-only
  `check_db` node that detects catalog duplicates from a descriptive
  brief carrying no canonical code, classifies the relationship into a
  closed set (`no_match`, `duplicate`, `same_concept_other_feed`,
  `transformation_overlap`, `adjacent_supersede_candidate`,
  `distinct_with_related`), and emits a structured verdict consumed by
  a downstream router.
- ADR 0020 (`docs/adr/0020-catalog-embeddings-for-semantic-search.md`)
  — pgvector columns on `concepts`, `series_families`, `series`;
  `text-embedding-3-small` at 1536 dimensions; service-function
  registration path (`register_concept`, `register_family`,
  `register_series`) shared by the bootstrap, the MCP write tool, and
  any future ingestion runner; `embedding_model` +
  `embedding_input_hash` versioning columns for mechanical staleness
  detection; and `macrodb embeddings backfill` as the only repair
  path. The read-only MCP gains `search_concepts`,
  `search_series_families`, and `search_series` backed by tag prefilter
  plus cosine similarity.
- `check_db_instructions` prompt added to
  `src/macro_foundry/onboarding_agent/prompts.py` as the agent-facing
  contract for the new node.

Deviation note: this is design only. No Alembic migration, no service
module, no MCP-tool extension, no graph wiring landed. Follow-up
issues to track: (a) Alembic migration for `pgvector` extension +
embedding columns + HNSW indexes; (b) `services/embeddings.py` and
`services/registration.py`; (c) refactor of
`src/macro_foundry/bootstrap/fred_us_macro.py` and the MCP write tool
to use the registration helpers; (d) MCP read-tool extension for the
three search tools; (e) `check_db` node wired into the graph in
`src/macro_foundry/onboarding_agent/1_scoping.ipynb`; (f) backfill
CLI command.

Committed as `6679fb5`.

### [2026-06-12] CLI/DB naming — standardized target vs role vocabulary

Breaking cleanup to keep environment targets separate from database roles:

- `EnvTarget` remains the single environment-target enum (`dev`, `test`,
  `staging`), while `macrodb_app` / `macrodb_owner` remain role names.
- Replaced the resolver surface with `app_url_for_target(target)` and
  `owner_url_for_target(target)`. Removed the previous resolver and
  onboarding-target alias paths rather than keeping compatibility shims.
- Renamed bootstrap result/parameter surfaces from `database` to `target`
  where the value is an `EnvTarget`; raw `database_url` remains only for
  explicit connection strings such as MCP serving.
- Updated current docs/examples away from `--database app|test`; historical
  tracker entries below still describe the surface as it existed when those
  entries were written.

Verification:

- `uv run pytest tests/macrodb/test_onboard_cli.py tests/macrodb/test_debug_bootstrap.py tests/macrodb/test_fred_bootstrap.py -q -m no_db`
  exited 0 with `12 passed, 5 deselected`.
- `uv run pytest tests/shared/test_config.py -q` exited 0 with `2 passed`
  after the planned `-m no_db` variant deselected both tests.
- `uv run ruff check` on the refactor-touched source and test files passed.
  Full `uv run ruff check src/macro_foundry tests` still fails on unrelated
  lint in the vendored `onboarding_agent/reference/deep_research_from_scratch`
  copy and pre-existing unrelated test lint.

### [2026-06-12] CLI — added `macrodb db migrate --target {dev|test}`

Plugged the ergonomic gap surfaced by the `series.alt_name` rollout:
`uv run alembic upgrade head` only ever touched `MACRODB_OWNER_URL`
(= `macrodb_dev`), so the test database silently drifted behind the
model whenever a migration landed locally, and `macrodb serve api
--target test` would 500 on any table the migration added a column to.

New surface:

```
macrodb db migrate --target {dev|test} [--revision REV] [--downgrade] [--json]
```

`--target` defaults to `dev`, matching the rest of the CLI. The
command resolves the owner-role URL for the selected target via a new
`owner_url_for_target` helper (reuses the database-name swap
pattern from `tests/conftest.py:_owner_test_url`), then runs Alembic
programmatically. Output is key=value (or JSON) and includes
before/after revisions so a no-op upgrade is obvious from a glance.

`alembic/env.py` now respects a pre-set `sqlalchemy.url` on the
Alembic Config and only falls back to `settings.db.owner_url` when
nothing is set, so terminal `uv run alembic upgrade head` continues to
work unchanged.

Verification:

- `uv run macrodb db migrate --target dev` → `before=0011 after=0011`
  (no-op, dev already at head).
- `uv run macrodb db migrate --target test --downgrade --revision 0010` →
  `before=0011 after=0010`.
- `uv run macrodb db migrate --target test --json` →
  `{"target":"test","direction":"upgrade","revision":"head","before":"0010","after":"0011"}`.
- Direct SQL probe against both URLs confirms `macrodb_dev` and
  `macrodb_test` are distinct physical databases and both carry the
  `series.alt_name` column.
- `uv run ruff check` clean across all touched files.
### [2026-06-11] Onboard CLI — GPT-5.4 OpenAI compatibility and FRED credential detection fixed

Updated the OpenAI-backed onboarding LLM wrapper so GPT-5/reasoning-model
chat completion calls send `max_completion_tokens` instead of the legacy
`max_tokens` parameter while preserving `max_tokens` for older chat models
such as `gpt-4o`. Replaced open `dict[str, Any]` structured-output fields
with closed DTOs so GPT-5.4 accepts the response schemas. Wired the production
credential-gap node through `settings.resolve_credential_ref("FRED_API_KEY")`
so a key present in `.env.local` resolves the FRED credential gap instead of
prompting the operator.

Verification:

- `uv run pytest tests/macrodb/test_llm_openai.py -q -m no_db` exited 0
  with `17 passed`
- `uv run ruff check src/macro_foundry/agent/llm_openai.py tests/macrodb/test_llm_openai.py`
  exited 0
- `uv run pytest tests/macrodb/ -q -m no_db` exited 0 with
  `225 passed, 85 deselected`
- `uv run macrodb onboard --target test`, input
  `onboard US FRED's M2 (M2SL)`, reached Gate 1 without rendering the
  `FRED_API_KEY` credential-required picker; diagnostic session saved as
  `onboard-c219e0bab780`

### [2026-06-11] Onboard CLI — test target allowed for local test-environment runs

Adjusted `macrodb onboard --target test` to run against the local test
environment while warning that it is non-durable and must not be treated as
the normal onboarding workflow target. Updated the CLI target docs and ADR
0017 command summary to match.

Verification:

- `uv run pytest tests/macrodb/test_onboard_cli.py -q -m no_db` exited 0
  with `11 passed`
- `uv run ruff check src/macro_foundry/cli/onboard.py tests/macrodb/test_onboard_cli.py`
  exited 0

### [2026-06-11] Issue 59 follow-up — Cohort contract, metadata skill trigger, and selector schema classification corrected

Closed the last-mile wiring gaps found in the post-completion review of issue 59:

- production `cohort_lookup` now normalizes both explicit FK hits
  (`family_id`, `concept_id`, `provider_id`) and researcher-style
  `{"kind": ..., "id": ...}` catalog hits before calling the MCP read tools,
  so empty cohort A is a genuine observation rather than a shape mismatch.
- the draft-proposal metadata skill trigger now uses graph-owned state:
  metadata rules load for the drafter before prose is generated, and seed
  exemplars load from `is_first_in_family == true` instead of the stale
  `reference_metadata.cohort_A_empty` key.
- `extraction_mode_classifier` now reads selector schemas through
  `get_selector_schema` as well as `list_selector_types`; ambiguous shapes route
  through the classifier-grade OpenAI path while clear registry matches remain
  deterministic.
- added a production-deps graph test proving a non-empty MCP cohort reaches the
  drafter prompt.

Verification:

- `uv run pytest tests/macrodb/test_production_deps.py -q -m no_db` exited 0
  with `12 passed`
- `uv run pytest tests/macrodb/test_skill_wiring.py tests/macrodb/test_skill_loader.py -q -m no_db`
  exited 0 with `14 passed`
- `uv run pytest tests/macrodb/test_reference_metadata_nodes.py -q -m no_db`
  exited 0 with `27 passed`
- `uv run ruff check src/macro_foundry/agent/production_deps.py src/macro_foundry/agent/llm_schemas.py src/macro_foundry/agent/graph.py src/macro_foundry/agent/skills.py tests/macrodb/test_production_deps.py tests/macrodb/test_skill_wiring.py tests/macrodb/test_skill_loader.py`
  exited 0
- `uv run pytest tests/macrodb/ -q -m no_db` exited 0 with
  `222 passed, 85 deselected`
- `uv run pytest tests/macrodb/ tests/shared/ -q` exited with
  `342 passed, 1 failed`; the failure was the pre-existing flaky
  `test_concurrency_advisory_warns_when_another_session_exists`, which passed
  immediately in isolation.

### [2026-06-11] Issue 59 — MCP-backed cohorts and selector-registry extraction classification

Replaced the two production dependency placeholders from issue 59:

- `build_production_dependencies` now injects a DB-backed `cohort_lookup` that
  resolves ADR 0013 cohort A/B/C from `existing_catalog_hits` through
  `MacrodbReadTools.find_sibling_series`, `list_series_for_concept`, and
  `list_provider_series_for_concept`; repeated rows are deduped before graph
  state receives `reference_metadata`.
- `is_first_in_family` remains graph-owned and is now based on genuine cohort A
  read-tool results in the production path, rather than `_empty_cohort_lookup`.
- `extraction_mode_classifier` now consults `MacrodbReadTools.list_selector_types`
  and treats matching registered selectors / known selector shapes as
  `config_only` before falling back to the custom-Python keyword signals.
- `approval_llm` remains the documented v1 pass-through from operator
  `pending_input` to `edit_instructions`; no architectural change made.

Verification:

- `uv run pytest tests/macrodb/test_production_deps.py -q -m no_db` exited 0
  with `8 passed`
- `uv run pytest tests/macrodb/test_reference_metadata_nodes.py -q -m no_db`
  exited 0 with `27 passed`
- `uv run ruff check src/macro_foundry/agent/production_deps.py tests/macrodb/test_production_deps.py`
  exited 0
- `uv run pytest tests/macrodb/ -q -m no_db` exited 0 with
  `217 passed, 85 deselected`

### [2026-06-11] Issue 57 (last mile) — Production dependency factory wired into CLI

Connected the OpenAI provider module to the real CLI path so `macrodb onboard`
no longer hits `_missing_graph_dependencies()`.

- `src/macro_foundry/agent/production_deps.py` (new) — `build_production_dependencies`
  factory: OpenAI LLM callables for all roles via `make_openai_llm_callable` /
  `make_openai_reviewer_callable`, Questionary-backed `gate_1_picker`, keyword-heuristic
  `extraction_mode_classifier`, empty-cohort `cohort_lookup` (v1 best-effort),
  pass-through `approval_llm` (pending_input → edit_instructions), `MacrodbWriteTools`
  and `_DbRunLogReader` for DB seams, `_FilePackageStore` to `~/.macrodb/packages/`,
  `SkillRegistry.from_directory(docs/skills/)` for accepted-skill loading
- `src/macro_foundry/agent/llm_schemas.py` — added `ApprovalOutput` and
  `TestReviewOutput` Pydantic schemas
- `src/macro_foundry/cli/onboard.py` — refactored to `_async_onboard` wrapper that
  opens a DB session, calls `build_production_dependencies`, and injects populated
  `OnboardingGraphDependencies` into `SessionRuntimeConfig`; `role_config_overrides`
  still passed through to `run_onboarding_session` for graph-level role logging
- Three existing CLI tests updated: `_patch_production_deps` helper patches the
  factory, session factory, engine, and `database_url_for_env_target` so
  argument-parsing unit tests don't need a real DB connection or OpenAI key
- `test_production_deps.py` (new) — 6 tests: type check, no-raising-stub guard,
  research_llm format via mock HTTP transport, governance_llm task_hint tiering,
  CLI deps-populated guard, end-to-end full graph through emit_package

Verification:

- `uv run ruff check src/macro_foundry/agent/production_deps.py src/macro_foundry/agent/llm_schemas.py src/macro_foundry/cli/onboard.py tests/macrodb/test_production_deps.py tests/macrodb/test_onboard_cli.py` exited 0
- `uv run pytest tests/macrodb/ -q -m no_db` exited 0 with `215 passed`
- `uv run pytest tests/macrodb/ tests/shared/ -q` exited 0 with `335 passed` (1 pre-existing flaky concurrency advisory test)

### [2026-06-10] Issue 27 — Small-edit subflow with uniqueness collision and Gate 2 dangerous-correction branch

Implemented the Gate 2 dangerous-correction path per issue 27:

- `Gate2Outcome` enum and `DangerousCorrectionPlan` Pydantic model (carries
  `collision_column`, `existing_code`, `proposed_code`, all affected-row
  categories, and `repair_strategy` from a closed three-value allowlist)
- `make_dangerous_correction_plan_node` — injects a planner LLM and records
  the impact analysis + repair plan in graph state
- `make_gate_2_wait_node` — same structural shape as Gate 1 (`Approve` /
  `Reject` / `Request changes`); `Approve` sets `gate_2_approved=True`, no
  LLM call; `Request changes` calls the approval LLM and loops to re-plan
- `make_dangerous_correction_executor_node` — applies only the approved repair
  plan via an injected `repair_fn`; rejects execution when `gate_2_approved`
  is not `True`; routine catalog writes are not permitted on this branch
- updated `apply_small_edit`: `rename` and `cancel` paths now clear
  `collision_choice` and restore the original proposal so
  `EDGE_NEXT_FROM_APPLY_SMALL_EDIT` routes back to `gate_1_wait` instead of
  `END`; `challenge_existing` preserves `collision_choice` for routing to
  `dangerous_correction_plan`
- new graph edges: `apply_small_edit → dangerous_correction_plan → gate_2_wait
  → dangerous_correction_executor → END`; `gate_2_wait` loops back to
  `dangerous_correction_plan` on `Request changes`
- `gate_2_picker`, `planner_llm`, and `repair_fn` added as optional injectable
  parameters to `build_onboarding_graph` (no-op defaults for backwards
  compatibility)
- `gate_2_outcome`, `gate_2_approved`, `gate_2_replan_instructions`,
  `dangerous_correction_plan`, `dangerous_correction_repair` added to
  `OnboardingGraphState` and `OnboardingCheckpointState`
- `skill-dangerous-correction` promoted from `stub` to `accepted` with the
  full publication-boundary test, trigger-condition inventory, repair-strategy
  decision criteria, Gate 2 semantics, executor scope constraint, and
  anti-pattern list distilled from `docs/series_catalog_governance.md` and
  `docs/series_onboarding_workflow.md`

Verification:

- `uv run ruff check src/macro_foundry/agent/gate.py src/macro_foundry/agent/graph.py src/macro_foundry/agent/onboarding_state.py tests/macrodb/test_dangerous_correction.py tests/macrodb/test_gate_1.py` exited 0
- `uv run pytest tests/macrodb/ -q -m no_db` exited 0 with `170 passed`
- `uv run pytest tests/macrodb/ tests/shared/ -q` exited 0 with `290 passed` (1 pre-existing flaky concurrency advisory test unaffected)

### [2026-06-10] Issue 58 — Skill loader wired into LLM node prompt assembly

Replaced all `_ = registry  # skill loading is wired in future slices` stubs
in the four LLM node factories with live `assemble_prompt` calls:

- `make_research_node` — wired with `skill_triggers=[]` (no triggers declared yet)
- `make_draft_proposal_node` — wired with `METADATA_STANDARDISATION_SKILL_TRIGGERS`;
  metadata-standardisation prose fires when `proposal.touches_prose == True` and
  the Seed exemplars subsection fires when `reference_metadata.cohort_A_empty == True`
- `make_governance_review_node` — wired with `GOVERNANCE_SKILL_TRIGGERS`;
  selector-conventions skill fires only when `extraction_mode == custom_python`
- `make_data_correctness_review_node` — wired with `skill_triggers=[]`

Each node now:
- calls `assemble_prompt(base_role_prompt="", node=..., state=..., registry=..., skill_triggers=...)`
- prepends skill bodies as a `system` message when the assembled text is non-empty
- derives `loaded_skills` from `assembled.state_update()` instead of hardcoding `[]`

`assemble_prompt` in `skills.py` updated to filter empty strings before joining
bodies, so `base_role_prompt=""` does not produce a leading `\n\n`.

Verification:

- `uv run ruff check src/macro_foundry/agent/graph.py src/macro_foundry/agent/skills.py tests/macrodb/test_skill_wiring.py` exited 0
- `uv run pytest tests/macrodb/test_skill_wiring.py -q -m no_db` exited 0 with `8 passed`
- `uv run pytest tests/macrodb/ -q -m no_db` exited 0 with `165 passed, 85 deselected`

### [2026-06-10] Issue 56 — Production onboarding graph assembled and wired into CLI loop

Promoted the injectable end-to-end onboarding graph to the canonical
`build_onboarding_graph` and wired `run_onboarding_session` / `macrodb onboard`
away from the hello-world graph. The session loop now seeds checkpoint metadata
with `aupdate_state`, invokes the canonical graph on operator input, preserves
resume behavior, consumes real `role_configs`, and exposes injectable graph
dependencies for tests and future live LLM/MCP wiring.

Graph assembly and cleanup:

- canonical graph now covers research → credential-gap wait → reference metadata
  → extraction-mode classification → draft → enum-gap wait → draft script
  placeholder → governance/data-correctness review → Gate 1 → request-change
  drafter loop / small-edit loop / reject terminal / approve executor path →
  apply_catalog → trigger_first_run → monitor_first_run → test_review →
  emit_package
- deleted the intermediate graph builders and smoke-specific edge functions from
  the public agent graph surface
- collapsed onboarding state to one `suggest_human_apply` key and removed the
  duplicate `harmonisation_items` TypedDict declaration
- narrowed evidence-filter validation catches in the graph from bare
  `Exception` to Pydantic `ValidationError`

Verification:

- `uv run pytest tests/macrodb/test_onboarding_smoke.py -q` exited 0 with
  `5 passed`
- `uv run pytest tests/macrodb/ -q -m no_db` exited 0 with
  `157 passed, 85 deselected`

### [2026-06-10] ADR 0017 — `macrodb` CLI interface standardisation implemented

Refactored the entire `macrodb` CLI surface per ADR 0017:

- **`EnvTarget` enum** added at `src/macro_foundry/db/env_target.py` with values
  `dev | test | staging`, replacing both `DatabaseTarget` (`app`/`test`) and
  `OnboardingTarget` (`dev`/`staging`). `database_url_for_env_target(EnvTarget)`
  is the single resolver. `prod` is deliberately absent.
- **`DatabaseTarget` removed** from `db/session.py` and `db/__init__.py`. All
  bootstrap, CLI, and test callers updated. `OnboardingTarget` becomes a shim
  alias (`OnboardingTarget = EnvTarget`) in `agent/onboarding_targets.py` so
  agent-layer callers remain unchanged.
- **`--target` flag everywhere.** `seed`, `db bootstrap`, `serve api`, and
  `onboard` all declare `--target` with the `Annotated[T, typer.Option("--flag")]`
  style. Per-command allowed subsets enforced at the CLI boundary (not in the
  resolver).
- **`macrodb db bootstrap`** — `bootstrap` moves under the `db` noun group.
  `db_app` and a nested `bootstrap_app` added to `_app.py`.
- **`macrodb serve api` / `macrodb serve mcp`** — single `serve` command replaced
  by two subcommands. `serve api` defaults `--reload` to `False`. `serve mcp`
  accepts `--write` to enable write tools and `--database-url` to override
  `--target`.
- **`macrodb-mcp` / `macrodb-mcp-write` console scripts removed** from
  `pyproject.toml`. MCP server entry point is now `macrodb serve mcp [--write]`.
  Standalone Typer app removed from `mcp/server.py`; `build_*_server()` functions
  remain.
- **`--reset --confirm` replaced by `--reset [-y]`** across `seed` and
  `db bootstrap`. Interactive `typer.confirm` with `--yes/-y` skip via shared
  `confirm_destructive()` helper.
- **`cli_error_handler` decorator** provides one `ValueError → Exit(2)` path
  shared across all commands. `print_result(result, as_json=)` renders
  space-separated `key=value` or JSON under a global `--json` flag.
- **`macrodb onboard`** — 18 per-role model flags (`--<role>-model`,
  `--<role>-deep-model`) replaced by repeatable `--model ROLE=NAME` and
  `--deep-model ROLE=NAME`. `--max-session-cost-usd` renamed `--cost-cap`.
- **`src/macro_foundry/cli/bootstrap.py` deleted** (replaced by `cli/db.py`).

Verification:

- `uv run ruff check` over all changed source and test files exited 0
- `uv run pytest tests/macrodb/ -q -m no_db` exited 0 with `157 passed`
- `uv run pytest tests/macrodb/ tests/shared/ -q` exited 0 with
  `277 passed, 1 pre-existing flaky concurrency advisory test`

### [2026-06-10] Issue 51 — HITL operator review + promotion of three `draft` skills to `accepted`

Operator-driven HITL acceptance gate (PRD #32). Reviewed and promoted the
three escalation/standardisation skills from `draft` to `accepted`, so the
runtime skill loader may now load them into role prompts:

- **`skill-credential-gap`** — reviewed the operator-instruction block at
  `credential_gap_wait`. During review, reconciled a contradiction between
  pre-check layer 3 and the "previously-blessed credential" anti-pattern
  (now gated on credential provenance), and dropped the unreachable
  `declined` resolution outcome (2-option picker has no coerce path; only
  `aborted` is a negative terminal). Matching consistency fixes applied to
  ADR 0016.
- **`skill-enum-gap-escalation`** — cross-checked against the credential-gap
  fixes; confirmed it has no analogous contradiction or vestigial outcome,
  and that its rendered `enum_gap_wait` block (Python diff + ADR 0005 Alembic
  template + resume command) is sound. No edits needed.
- **`skill-metadata-standardisation`** — signed off on the five seed exemplars
  and the geography-prefix pattern. Corrected against V3 source of truth:
  replaced fabricated columns (`basket`, `household_scope`, `unit_code`) with
  real `series` enum columns; fixed `series.name` separator to en-dash
  (U+2013, matching all exemplars); scoped the retroactive-edit anti-pattern
  to cosmetic rules so it no longer collides with the `factual_incompleteness`
  trigger; relaxed the `variant` rule to permit a compact qualifier list;
  pointed the enum-escalation note at ADR 0014 instead of "deferred."

Also flipped `status:` frontmatter + body status lines in all three skills,
updated the `docs/skills/README.md` inventory (and removed a duplicate
`skill-enum-gap-escalation` row), and updated the Seed-exemplars status note.

Blocked-by #43, #48, #49 all closed prior to this work. Closes #51.

### [2026-06-10] Issue 52 — End-to-end FRED onboarding smoke

Implemented five deterministic integration smokes for the gated onboarding
runtime against the migrated FRED `json_path` selector path:

- added a full injectable `build_onboarding_smoke_graph` spanning research,
  reference metadata, extraction-mode classification, draft proposal,
  enum/credential gap waits, reviewer nodes, Gate 1, `apply_catalog`,
  first-run trigger/monitor, test review, and `emit_package`
- extended draft feed payloads with `selector_config` and persisted that config
  to `ingestion_feed_members`
- replaced the write-tool `trigger_feed_execution` stub with a call to the
  selector-registry `execute_feed` runtime using a recorded provider payload
- carried `first_run_payload`, `first_run_run_date`, and
  `credential_gap_resolutions` through graph state so executor nodes can resume
  and persist access metadata
- passed approved harmonisation items into the transactional catalog write for
  `series.description` updates
- added `tests/macrodb/test_onboarding_smoke.py` covering happy path,
  harmonisation, enum-gap resume, credential-gap resume without secret leakage,
  and suggest-human-apply mark-applied workflow

Verification:

- `uv run pytest tests/macrodb/test_onboarding_smoke.py -q` exited 0 with
  `5 passed`
- `uv run pytest tests/macrodb/test_onboarding_smoke.py tests/macrodb/test_executor_nodes.py tests/macrodb/test_apply_catalog.py tests/macrodb/test_write_mcp.py tests/macrodb/test_reference_metadata_nodes.py -q`
  exited 0 with `54 passed`
- `uv run ruff check src/macro_foundry/agent/proposal.py src/macro_foundry/agent/executor.py src/macro_foundry/agent/catalog.py src/macro_foundry/agent/graph.py src/macro_foundry/mcp/write_tools.py tests/macrodb/test_onboarding_smoke.py`
  exited 0

### [2026-06-10] Issue 48 — Enum-gap escalation vertical slice

Implemented the ADR 0014 enum-gap escalation path:

- replaced the placeholder `EnumGapProposal` with the evidence-bearing,
  allowlisted series-methodology enum shape; non-allowlisted enum paths are
  rejected by Pydantic
- `draft_proposal` now drops invalid/evidence-incomplete enum gaps before state,
  clears `proposal` when valid gaps remain, passes `coerce_hints` /
  `coerce_rationales` on rerun, and suppresses gaps for coerced enum paths
- added `enum_gap_wait` helpers that render Python enum diff, ADR 0005-style
  Alembic CHECK migration template, exact resume command, three-option picker,
  Python+DB resume verification, renamed-value reconciliation, and
  decline-and-coerce state updates
- routed drafter output with gaps to `enum_gap_wait` before script drafting;
  pause/abort stop the graph, resolved/coerced gaps rerun the drafter
- governance reviewer prompts now include `enum_gap_proposals` so the
  enum-gap skill's three conditions and anti-pattern list can become reviewer
  findings
- added governance enum values `Action.SUGGEST_ENUM_ADDITION`,
  `TargetType.ENUM_VALUE`, and `ValidationStatus.DECLINED_BY_OPERATOR`, plus
  migration `0010_enum_gap_governance_values.py`
- `record_enum_gap_proposal` now writes one independent schema-change audit row
  with `target_type=ENUM_VALUE` and `action=SUGGEST_ENUM_ADDITION`

Verification:

- `uv run pytest tests/macrodb/test_research_draft_nodes.py tests/macrodb/test_enum_gap_wait.py tests/macrodb/test_reference_metadata_nodes.py::test_draft_proposal_conditional_edge_prioritizes_enum_gap_wait tests/macrodb/test_reviewer_nodes.py::test_governance_review_prompt_includes_enum_gap_proposals tests/macrodb/test_write_mcp.py::test_record_enum_gap_proposal_writes_independent_enum_value_audit_row -q`
  exited 0 with `25 passed`
- `uv run pytest tests/macrodb/test_research_draft_nodes.py tests/macrodb/test_enum_gap_wait.py tests/macrodb/test_reference_metadata_nodes.py tests/macrodb/test_reviewer_nodes.py tests/macrodb/test_onboarding_state.py tests/macrodb/test_escalation_helpers.py -q -m no_db`
  exited 0 with `77 passed`
- after local test-DB constraint drift was patched, `uv run pytest tests/macrodb/test_write_mcp.py::test_record_enum_gap_proposal_writes_independent_enum_value_audit_row -q`
  exited 0 with `1 passed`
- `uv run ruff check src/macro_foundry/agent/enum_gap.py src/macro_foundry/agent/graph.py src/macro_foundry/agent/onboarding_state.py src/macro_foundry/enums/governance.py src/macro_foundry/mcp/write_tools.py tests/macrodb/test_enum_gap_wait.py tests/macrodb/test_research_draft_nodes.py tests/macrodb/test_reference_metadata_nodes.py tests/macrodb/test_reviewer_nodes.py tests/macrodb/test_write_mcp.py alembic/versions/0010_enum_gap_governance_values.py`
  exited 0

Local verification note:

- this host's shared `macrodb_test` was already stamped at revision `0009` from
  another worktree's credential-gap enum widening, so Alembic did not rerun the
  enum-gap migration until the test DB was reconciled; for local verification
  only, the test DB CHECK constraints were patched to include both the
  credential-gap values and the enum-gap values. A fresh database applies the
  committed migration chain normally.

### [2026-06-10] Issue 49 — Credential-gap escalation partial implementation

Implemented the deterministic credential-gap slice per ADR 0016:

- added `AuthScheme` plus provider access metadata columns
  (`providers.auth_scheme`, `providers.rate_limit_config`) in models,
  schemas, canonical ER source, and migration `0009`
- widened governance enums for credential-gap audit rows:
  `Action.SUGGEST_CREDENTIAL_PROVISIONING`,
  `TargetType.CREDENTIAL_REF`, and
  `ValidationStatus.DECLINED_BY_OPERATOR`
- added typed credential-gap proposal/resolution models and a pure
  `CredentialPrecheck` helper covering existing-provider credential refs,
  env-var checks, probe outcomes, and session-local cache behavior
- added `credential_gap_wait` deterministic node factory with only
  Apply later / Abort picker options; successful resume probe records a
  resolution without ever returning the credential value
- updated research node output filtering so credential-gap proposals missing
  evidence are dropped before reaching state
- updated write tools so credential-gap audit rows use the credential-specific
  action/target/status, and so Gate 1 can write resolved provider access
  metadata after approval
- updated `apply_catalog` to apply credential-gap resolutions after the main
  catalog write

Verification:

- `uv run ruff check ...` over touched source and test files exited 0
- `uv run pytest tests/macrodb/test_credential_gap.py tests/macrodb/test_apply_catalog.py tests/macrodb/test_research_draft_nodes.py -q -m no_db` exited 0 with `24 passed`
- `uv run pytest tests/shared/test_schemas.py tests/macrodb/test_write_mcp.py::test_record_credential_gap_proposal_writes_credential_ref_audit_item tests/macrodb/test_write_mcp.py::test_apply_credential_gap_resolutions_updates_existing_provider_access_metadata -q` exited 0 with `10 passed`

### [2026-06-10] Issue 50 — Post-Gate-1 first-run executor nodes

Implemented the no-DB executor-node vertical slice for issue #50:

- added `src/macro_foundry/agent/executor.py` with node factories for
  `trigger_first_run`, `monitor_first_run`, `test_review`, and `emit_package`
- `trigger_first_run` reads the `applied_catalog.feed_id`, calls the write-tool
  `trigger_feed_execution`, records `first_run.run_log_id`, and is idempotent
  on resume when `first_run.run_log_id` already exists
- `monitor_first_run` re-queries the run-log reader by persisted
  `first_run.run_log_id` and refreshes the first-run summary instead of
  restarting from transient polling state
- `test_review` classifies tolerated first-run warnings separately from hard
  failures using the workflow policy, then calls an injected reviewer seam for
  the human-readable synthesis
- `emit_package` builds and persists the test-approved onboarding package shape
  with proposal summary, staging canonical rows, reviewer findings, first-run
  summary, tolerated warnings, `thread_id`, and `change_proposal_id`
- `apply_catalog` now exposes an `applied_catalog` state block carrying the
  write-tool IDs needed by downstream executor nodes
- onboarding checkpoint state and graph state now carry `applied_catalog`,
  `first_run`, `test_review`, and `onboarding_package` so crashes between
  executor nodes leave recoverable state

Verification:

- `uv run pytest tests/macrodb/test_onboarding_state.py tests/macrodb/test_apply_catalog.py tests/macrodb/test_executor_nodes.py -q -m no_db` exited 0 with `18 passed`
- `uv run pytest tests/macrodb/ -q -m no_db` exited 0 with `139 passed, 77 deselected`
- `uv run ruff check src/macro_foundry/agent/executor.py src/macro_foundry/agent/catalog.py src/macro_foundry/agent/graph.py src/macro_foundry/agent/onboarding_state.py tests/macrodb/test_executor_nodes.py tests/macrodb/test_apply_catalog.py tests/macrodb/test_onboarding_state.py` exited 0

Remaining integration boundary:

- this slice uses injected write-tool, run-log reader, reviewer, and package
  store seams; the full database-backed Gate 1 approval -> FRED first-run ->
  emit-package integration test still needs the concrete first-run trigger
  runtime path to provide a real payload/fetch boundary.

### [2026-06-10] Issue 55 — Admin landing page with live count cards

Implemented the admin landing page vertical slice per issue #55:

- added `src/macro_foundry/backend/admin/stats.py` as a pure async module
  with no SQLAdmin/FastAPI/Starlette imports — only `sqlalchemy` and project
  models; `admin_stats(AsyncSession) -> AdminStats` returns a dataclass carrying
  `concept_count`, `series_family_count`, `series_count_by_origin_type` (keyed
  by all three `OriginType` values), `observation_count`, `provider_count`, and
  `ingestion_feed_count`
- added `src/macro_foundry/backend/admin/templates/landing.html` extending
  `sqladmin/layout.html`; contains the static intro copy in the domain
  vocabulary from `CONTEXT.md`, a six-card stat row, and a link list to
  Concepts, Series Families, Series, Providers, and Observations
- replaced `Admin` with a private `_MacroFoundryAdmin(Admin)` subclass in
  `register.py` that overrides the built-in `index` method; the override calls
  `admin_stats` and renders `landing.html` — this is the correct sqladmin
  mechanism for a custom index page (the `BaseView + expose("/")` pattern
  described in the issue cannot override the default index route because
  Starlette first-matches on routes and the default `Route("/")` is registered
  at construction time; the sqladmin `index` docstring explicitly invites this
  override approach)
- passed the templates directory as an absolute path via `templates_dir` so
  the Jinja loader finds `landing.html` regardless of server CWD
- added migration `0008_governance_enum_widenings.py` to the worktree (copied
  from issue-47 branch which had applied it to the shared test DB)
- added two test modules:
  - `tests/macrodb/test_admin_stats.py` — three unit tests covering result
    shape, origin-type key completeness, and count delta after mutation
  - `tests/macrodb/test_admin_landing.py` — four integration tests covering
    200 response, intro headline, six card labels, and unauthenticated redirect

Deviation note:

- unauthenticated `/admin/` returns 302 (redirect to login), not 401 — the
  issue spec said 401, but the `login_required` decorator redirects to the
  login form; this is consistent with all other protected admin routes and the
  existing `test_admin_redirects_to_login_when_not_authenticated` test

Verification:

- `uv run ruff check src/macro_foundry/backend/admin/stats.py src/macro_foundry/backend/admin/register.py tests/macrodb/test_admin_stats.py tests/macrodb/test_admin_landing.py` exited 0
- `uv run pytest tests/macrodb/test_admin_stats.py tests/macrodb/test_admin_landing.py -q` exited 0 with `7 passed`
- `uv run pytest tests/macrodb/ tests/shared/ -q` exited 0 with `228 passed` (1 pre-existing flaky test in `test_onboard_cli.py` is independent)

---

## Current phase

**Phase 13 — Neon parity verification** (next up).

Phase 12 is now complete. The local test harness now seeds `macrodb_test` once
per session, isolates each test with transaction rollback, and covers the
migration chain, seed idempotency, CRUD generator, constraint surface,
hand-written routes, admin auth, and one end-to-end API smoke before the final
Neon parity pass.

Issue 13 has implemented the canonical series hierarchy portion of ADR 0010.
Issue 15 has documented the onboarding and governance rules that keep hierarchy
enrichment and weak provider locators under explicit review. Issues 17, 16, and
18 have implemented request-level feed metadata, member-level run outcomes, and
member-level observation provenance. Issue 14 adds a minimal debug smoke path to
initialize and inspect that redesigned stack.

## Phase status

| Phase | Title                          | Status      |
| ----- | ------------------------------ | ----------- |
| 0     | Agent infrastructure           | ✅ Complete |
| 1     | Repo bootstrap                 | ✅ Complete |
| 2     | Docker + Postgres + roles      | ✅ Complete |
| 3     | Config + session + base        | ✅ Complete |
| 4     | Enums                          | ✅ Complete |
| 5     | Models                         | ✅ Complete |
| 6     | Alembic + initial migrations   | ✅ Complete |
| 7     | Pydantic schemas               | ✅ Complete |
| 8     | Seed data + CLI                | ✅ Complete |
| 9     | CRUD generator + simple routes | ✅ Complete |
| 10    | Hand-tuned routes              | ✅ Complete |
| 11    | SQLAdmin                       | ✅ Complete |
| 12    | Tests                          | ✅ Complete |
| 13    | Neon parity verification       | ⏳          |

## Log

### [2026-06-10] Issue 47 — Write-enabled MCP server, apply_catalog node, suggest_human_apply executor skip, SQLAdmin mark-applied action

Implemented the post-Gate-1 write path and operator tooling per issue 47:

- `MacrodbWriteTools` service class with 7 async methods:
  `propose_create_series`, `record_suggest_human_apply`, `mark_proposal_outcome`,
  `apply_approved_proposal`, `trigger_feed_execution` (stub, slice 17),
  `record_enum_gap_proposal` (stub, slice 14), `record_credential_gap_proposal` (stub, slice 15)
- `build_write_enabled_server()` wires all 7 tools and commits after each write; `build_read_only_server()` unchanged
- `macrodb-mcp-write` console script added as a dedicated entry point for the write-enabled server
- `make_apply_catalog_node()` reads gate-1-approved state, calls `propose_create_series`, and records
  `suggest_human_apply` items as `PENDING_HUMAN_APPLY` — never auto-applies them; guards on `gate_1_approved=True`
- `ChangeProposalItemAdmin.mark_applied` SQLAdmin action: flips `PENDING_HUMAN_APPLY` items to
  `APPLIED_BY_OPERATOR` and stamps `proposal.applied_at`; returns `RedirectResponse` (303)
- `ChangeProposal` model gains `applied_by` and `source_agent_session_id` columns
- Migration 0008 widens `action` and `validation_status` VARCHAR columns on `change_proposal_items`
  to 19 chars (raw SQL — `op.alter_column` silently failed to widen on psycopg3), drops and re-creates
  named CHECK constraints to include `suggest_human_apply` / `pending_human_apply` / `applied_by_operator`

Enums added:
- `Action.SUGGEST_HUMAN_APPLY`
- `ValidationStatus.PENDING_HUMAN_APPLY`, `ValidationStatus.APPLIED_BY_OPERATOR`

`DraftProposal` schema extended so `propose_create_series` can write actual catalog rows:

- `DraftSeries` gains three required fields (`temporal_stock_flow`, `unit_scale`,
  `seasonal_adjustment`) and optional fields mirroring the full `series` column set;
  `annualized`, `origin_type` (`"ingested"`), `is_active` have sensible defaults
- `DraftSeriesSource.provider_code` renamed to `provider_name` — maps to `Provider.name`
  (no `code` column exists on `providers`); adds `provider_role` and `priority` with defaults
- `DraftIngestionFeed` gains required `feed_method` and `is_active` (default True)
- `DraftFamilyMember` gains `is_primary` (default True)

`propose_create_series` now performs the full transactional catalog write:
Geography lookup → get-or-create Concept → get-or-create SeriesFamily → Series →
SeriesFamilyMember → Provider/ProviderCatalog lookup → SeriesSource → IngestionFeed →
IngestionFeedMember → optional hierarchy edges → audit ChangeProposal with
`status=APPLIED` and `applied_at` stamped (Gate 1 approval already happened in state).

Tests: 13 new passing total (integration test AC #6 added, 2 existing write-tool DB
tests updated to use full `DraftProposal` payloads and assert `status=APPLIED`).
Pre-existing cross-test pollution (`test_observations_routes` → `test_concurrency_advisory`) confirmed
on base branch — not introduced by this issue.

Verification:

- `uv run pytest tests/macrodb/test_write_mcp.py tests/macrodb/test_apply_catalog.py -q` exited 0 with `13 passed`
- `uv run pytest tests/macrodb/ -q` exited 0 with `201 passed, 1 pre-existing failure`

### [2026-06-10] Issue 45 — Gate 1 wait node, approval_parse, apply_small_edit, un-approval window

Implemented the Gate 1 interrupt slice per issue 45 / ADR 0011 approval semantics:

- `gate_1_wait` renders a three-section Gate 1 summary (new series /
  harmonisation companion items / suggest-for-human-apply) per ADR 0013;
  picker is injected so the node is fully testable without Questionary
- picker options are `Approve / Reject / Request changes` at cycle 1–2; at
  cycle 3 `Request changes` is replaced by `Permit further cycle`
- `approval_parse` path (approval_llm) is called only inside `Request changes`;
  `Approve` and `Reject` make no LLM call
- `apply_small_edit` applies a textual edit to the in-memory proposal, runs
  a uniqueness pre-check via injected `unique_checker`, then:
  - no collision → clears `gate_1_outcome` so `gate_1_wait` re-issues picker
  - collision → injected `collision_picker` renders three-way choice:
    rename / challenge_existing / cancel; challenge_existing sets
    `gate_2_escalation=True`
- `make_unapprove_node` rolls `gate_1_approved` back to `False` while
  `gate_1_applied=False`; after `apply_catalog` writes (`gate_1_applied=True`)
  sets `unapprove_rejected=True` instead — revocation becomes a correction
  proposal post-apply
- `is_structural_edit` classifies instruction text by keyword so structural
  edits (frequency, methodology, hierarchy, selector config) route back
  through the full drafter cycle, not the small-edit subflow

State fields added to `OnboardingGraphState` and `OnboardingCheckpointState`:
`harmonisation_items`, `suggest_human_apply_items`, `gate_1_outcome`,
`gate_1_approved`, `gate_1_applied`, `small_edit_instructions`,
`collision_choice`, `collision_detail`, `gate_2_escalation`, `unapprove_rejected`.

Verification:

- `uv run pytest tests/macrodb/test_gate_1.py -q -m no_db` exited 0 with `16 passed`
- `uv run pytest tests/macrodb/ -q -m no_db` exited 0 with `97 passed`
- `uv run ruff check src/macro_foundry/agent/gate.py src/macro_foundry/agent/graph.py src/macro_foundry/agent/onboarding_state.py tests/macrodb/test_gate_1.py` exited 0

### [2026-06-10] Issue 44 — Reviewer fan-out: governance + data_correctness implemented

Implemented the two-reviewer parallel fan-out per ADR 0015:

- added `ReviewBundle` model (`specialty`, `findings`, `review_cycle`,
  `bounce_to_drafter`) with `Literal` specialty validation in
  `src/macro_foundry/agent/review.py`
- added `governance_review`, `data_correctness_review`, `extraction_mode`,
  and `review_cycle` fields to `OnboardingGraphState` and
  `OnboardingCheckpointState`
- `make_governance_review_node`: writes `ReviewBundle(specialty="governance")`,
  increments `review_cycle`, sets `task_hint="selector_code_review"` when
  `extraction_mode == "custom_python"`, records `LLMCallRecord` with task_hint,
  enforces read-only tool binding via `bound_tools` frozenset excluding write tools
- `make_data_correctness_review_node`: writes `ReviewBundle(specialty="data_correctness")`,
  enforces same read-only tool binding
- `build_reviewer_fanout_graph`: compiles both reviewer nodes as parallel START
  branches — exactly two LLM calls regardless of `extraction_mode`
- `review_cycle` increments continuously; soft cap of 3 is visible via
  `bundle.review_cycle == 3`

All six acceptance criteria from issue 44 satisfied:
- ✅ Exactly two parallel reviewer nodes
- ✅ Read-only enforcement via bound_tools frozenset
- ✅ Governance conditional selector skill fires only for custom_python; task_hint set
- ✅ ReviewBundle per reviewer under specialty headings
- ✅ Review cycle counter visible in state
- ✅ Integration tests: config_only (2 calls, no task_hint) and custom_python
  (2 calls, governance gets task_hint=selector_code_review)

Verification:

- `uv run pytest tests/macrodb/test_reviewer_nodes.py -q -m no_db` exited 0 with
  `18 passed`
- `uv run pytest tests/macrodb/ -q -m no_db` exited 0 with `81 passed`
- `uv run ruff check src/macro_foundry/agent/graph.py src/macro_foundry/agent/review.py src/macro_foundry/agent/onboarding_state.py tests/macrodb/test_reviewer_nodes.py` exited 0

### [2026-06-10] Issue 39 — Read-only macrodb MCP server implemented

Implemented the read-only `macrodb-mcp` slice for ADR 0011 / PRD #32:

- added the `macrodb-mcp` console script, serving a FastMCP stdio process with
  `--database-url` so the same binary can target different macrodb databases
- added a read-only semantic tool service for `lookup_concept`, `lookup_family`,
  `find_sibling_series`, concept/provider cohort lookups, selector registry
  discovery, selector-config validation, and enum CHECK-constraint value lookup
- kept MCP argument validation on Pydantic schemas and reused existing
  application read schemas for catalog results
- enforced a read-only tool binding that rejects write-tool registration
- covered each read tool with smoke tests against `macrodb_test`, including
  `list_enum_values` parsing the real named CHECK constraint in Postgres

### [2026-06-10] Issue 40 — Shared escalation helpers implemented

Added the reusable `agent/escalation/` helper layer for ADR 0014/0016
gap wait nodes:

- `picker.py` renders two-option credential-gap and three-option enum-gap
  Questionary pickers with structured outcomes and inline operator
  instruction blocks
- `lifecycle.py` exposes pause/exit and resume-walk helpers that preserve
  checkpoint position and verify only unresolved gaps
- `audit.py` emits one independent `change_proposals` audit row plus one
  item row per gap through a narrow store protocol, with caller-supplied
  action, target type, proposed payload, and validation lifecycle values
- added focused no-DB tests covering picker dispatch, pause/resume walking,
  and fake-store audit emission

### [2026-06-10] Issue 37 — Role configs and LLM call telemetry initialized

Added the v1 typed onboarding-agent role configuration slice:

- `RoleConfig` / `RoleOverride` definitions with OpenAI-bound defaults for
  researcher, proposal drafter, script drafter, validator, governance reviewer,
  data correctness reviewer, approval parser, test reviewer, and dangerous
  correction planner
- no standalone `selector_reviewer`; governance has a
  `selector_code_review` task entry for ADR 0015 routing
- within-role model resolution through `task_hint`
- session-local CLI model overrides through `--<role>-model` and
  `--<role>-deep-model`
- append-only `llm_calls` checkpoint state records for model, tokens, cost
  estimate, latency, and tool calls

Verification:

- `uv run pytest tests/macrodb/test_agent_roles.py tests/macrodb/test_onboard_cli.py tests/macrodb/test_onboarding_state.py -q`
- `uv run ruff check src/macro_foundry/agent src/macro_foundry/cli/onboard.py tests/macrodb/test_agent_roles.py tests/macrodb/test_onboard_cli.py tests/macrodb/test_onboarding_state.py`

### [2026-06-10] Issue 38 — Skill registry and state-predicate loader implemented

Added the first runtime skill-loading slice for the gated onboarding agent:

- Markdown skill registry reads `docs/skills/*.md` frontmatter and loads only
  `status: accepted` skills
- prompt assembly evaluates node-declared `SkillTrigger` predicates against
  current graph state and appends skill bodies in trigger order
- `GOVERNANCE_SKILL_TRIGGERS` includes the ADR 0015 conditional
  `skill-ingestion-selector-conventions` load for
  `extraction_mode == "custom_python"`
- `METADATA_STANDARDISATION_SKILL_TRIGGERS` supports the conditional
  `Seed exemplars` subsection load when
  `reference_metadata.cohort_A_empty == true`
- assembled prompts expose a `loaded_skills` state update carrying skill id,
  trigger id, node, and optional subsection title
- onboarding checkpoint state now validates `loaded_skills` as append-only
- existing `docs/skills/skill-*.md` files now include status frontmatter while
  retaining their human-readable status sections

Verification:

- `uv run pytest tests/macrodb/test_skill_loader.py tests/macrodb/test_onboarding_state.py -q`
- `uv run pytest -q`
- `uv run ruff check .`

### [2026-06-10] Issue 36 — Second-wave ingestion selectors implemented

Implemented the ADR 0012 second-wave selector roster:

- added `csv_column` for file-method CSV payloads, including delimiter/BOM
  header handling, missing-value tokens, empty-data reporting, and CSV-shaped
  provider error wrappers
- added `censtatd_json` for Hong Kong CenStatD JSON payloads, including
  LZ-string request-param preparation, code-length hierarchy filtering,
  monthly period parsing, empty-data reporting, and CenStatD error wrappers
- added `estat_value_filter` for Japan e-Stat `getStatsData` payloads, including
  exact multi-dimensional value filtering, e-Stat monthly time-code parsing,
  single-object/list `VALUE` handling, empty-data reporting, and
  `RESULT.STATUS != 0` provider errors
- registered all three selectors in the runtime selector registry

### [2026-06-10] Issue 35 — FRED bootstrap migrated to generic runtime

Migrated the curated FRED U.S. macro bootstrap off the bespoke
`ingestion/runners/fred_series.py` path and onto the ADR 0012 generic runtime:

- FRED feed members now use `selector_type = "json_path"` with selector config
  carrying the FRED series id, metadata endpoint, observations endpoint,
  records path, period anchor field, value field, missing-value tokens, curated
  frequency, and frequency map
- the bootstrap still uses the FRED client for provider fetches and metadata
  validation, then hands a FRED-shaped payload to `execute_feed(...)`
- the generic runtime now preserves snapshot-vintage skip behavior by comparing
  parsed observations against latest stored observations before writing
- member-level run diagnostics now come from the selector runtime and preserve
  observation provenance through `ingestion_run_log_members`
- removed the obsolete `src/macro_foundry/ingestion/runners/fred_series.py`
  module and stale exports
- added a runtime integration regression for the recorded FRED-shaped JSON-path
  fixture

### [2026-06-10] Issue 33 — Generic ingestion runtime and json_path selector implemented

Implemented the first ADR 0012 runtime slice:

- added `src/macro_foundry/ingestion/runtime/runner.py` as the generic feed
  executor that reads active `ingestion_feed_members`, dispatches by
  `selector_type`, and writes feed-level plus member-level run logs
- added the selector contract types and registry under
  `src/macro_foundry/ingestion/runtime/`
- added the `json_path` selector with config validation, FRED-shaped payload
  extraction, empty-data handling, and defensive parsing for provider error
  wrappers returned as successful HTTP payloads
- extracted provider-agnostic period bounds into
  `src/macro_foundry/ingestion/runtime/calendar.py` and made the existing FRED
  provider helper delegate to it
- covered the work with selector, calendar, one-member runner, and multi-member
  runner tests

### [2026-06-10] Issue 34 — Onboarding agent foundation slice implemented

Added the first runtime slice for the gated onboarding agent from ADR 0011:

- `macrodb onboard` Typer command with `--target {dev,staging}` and `--resume`
  support; `prod` and `test` are rejected by Typer enum parsing
- typed `Channel` abstraction plus a Rich/Questionary CLI implementation
- hello-world LangGraph state machine with checkpoint-backed save/resume and
  transcript replay through a fake-channel smoke test
- Pydantic checkpoint state records for immutable session metadata and
  append-only `raw_messages`, `transcript`, and `node_transitions`
- PostgresSaver wiring scoped to the `langgraph` schema via connection
  `search_path`
- Alembic migration `0007` creating the `langgraph` schema and current
  checkpoint tables as `macrodb_owner`, with app-role DML grants but no app-role
  schema DDL grant

Verification:

- `uv run pytest tests/macrodb/test_onboard_cli.py tests/macrodb/test_onboarding_state.py -q`
- `uv run pytest tests/shared/test_migrations.py -q`
- `uv run ruff check .`

### [2026-06-10] Reviewer role consolidation (ADR 0015) and credential-gap escalation (ADR 0016) closed

Closed two design threads in one `/grill-with-docs` pass, both arising
from a holistic review of issue #19's staleness against ADRs 0011–0014.

**ADR 0015 — Reviewer role consolidation.** Two parallel reviewer roles
in v1 (governance + data_correctness) instead of three. Selector code
review folded into governance as a conditional skill load when
`extraction_mode == custom_python`, with `task_hint = selector_code_review`
routing to a code-reviewing model via the existing within-role tiering
mechanism from ADR 0011. Common case stays at 2 LLM calls; rare
`custom_python` case drops from 3 to 2. The structural property
"reviewer cannot write" is unchanged; it is enforced by MCP tool
binding, not by role count. Partially amends ADR 0011's reviewer
decision; the rest of ADR 0011 stands.

**ADR 0016 — Credential-gap escalation.** New sibling escalation
pattern mirroring ADR 0014 (enum-gap) for the case where the agent
cannot reach a provider because authentication material is missing or
invalid. Detection at `research` after a three-layer pre-check
(existing `credentials_ref` → `os.environ` → real probe), cached per
session. New `credential_gap_wait` node with 2-option picker
(`Apply later (pause)` + `Abort`); no "Decline and override" because
the probe is ground truth. Provider-row writes deferred to Gate 1
`apply_catalog` (asymmetric with enum-gap, principled because the gate
invariant forbids pre-Gate-1 catalog writes). New schema deltas: new
`Action.suggest_credential_provisioning`, new `TargetType.CREDENTIAL_REF`,
new `AuthScheme` enum, new columns on `providers`
(`auth_scheme`, `rate_limit_config`); `credentials_ref` confirmed in
CONTEXT.md and added to the model during implementation. Credential
value never enters macrodb, audit rows, state, or logs. The
escalation-gap pattern (shared shape: enum-gap + credential-gap) is
documented in the workflow doc as a pattern, not abstracted into one
node — distinct nodes preserve per-kind audit queryability and
per-kind evolution.

**Operational defaults locked for #32 PRD** (no ADRs; will land in the
new PRD's operational-defaults section):

- LLM cost: log per-call cost in `llm_calls`; no enforcement; CLI flag
  `--max-session-cost-usd` as hard cap.
- Retry on transient LLM failure: three retries with exponential
  backoff per call; surface on exhaustion; checkpoint preserves
  position.
- Probe fetch timeouts: 30s per fetch; recorded as a node-level error.

**Deferred to its own tracker:** concurrency semantics for parallel
`macrodb onboard` sessions, filed as
[#31](https://github.com/lckdairesearch/macro_foundry/issues/31).

**Implication for PRD #32 and issue slicing.** Issue #19 is now
materially stale across five places (node inventory, state schema,
MCP tool surface, schema deltas, skill inventory). The new PRD is
slot #32 (slot #31 was taken by the concurrency tracker). Child
issues #22, #23, #24, #27 should be closed and re-sliced under #32;
#20, #21, #25, #28, #30 are still correct and can be re-linked; #26
should be re-scoped per ADR 0015; #29 re-scoped per the new state
schema.

Documentation updated:

- new ADR `docs/adr/0015-reviewer-role-consolidation.md`
- new ADR `docs/adr/0016-credential-gap-escalation.md`
- new skill `docs/skills/skill-credential-gap.md` at `draft`
- `CONTEXT.md` — new glossary entry **Credential gap**
- `docs/series_onboarding_workflow.md` — Reviewers section updated to
  reflect two-role design; new Credential-gap escalation section;
  node inventory updated (added `credential_gap_wait`, removed
  `selector_review` as a separate node); read-only enforcement
  clarified
- inventory updates in `docs/adr/README.md` and
  `docs/skills/README.md`

### [2026-06-10] Enum-gap escalation design ratified as ADR 0014

Closed a `/grill-with-docs` session on how the gated onboarding agent
handles structural fields whose vocabulary cannot represent a
candidate series. Picked up directly from the parked-thread handoff
left by the metadata-standardisation session.

Decisions captured:

- **Scope:** enum-value gaps only on a closed allowlist of
  series-methodology enums in `src/macro_foundry/enums/series.py`
  minus `OriginType` — `Frequency`, `SeasonalAdjustment`, `Measure`,
  `MeasureHorizon`, `UnitKind`, `UnitScale`, `PriceBasis`,
  `ReferenceKind`, `TemporalStockFlow`. Column-shaped gaps abort
  with reason `schema_deficiency` and are deferred to a separate
  ADR-shaped decision.
- **Detection site:** inside `draft_proposal` as a structured output
  field (`enum_gap_proposals: list[EnumGapProposal]`), no new
  detection node. Router after the drafter reads a typed state
  field; the principle that routing must not parse generative
  output is preserved without adding a sibling deterministic node.
- **Human interrupt:** new node `enum_gap_wait`, distinct from
  Gate 1. Renders proposed value(s), rationale, cited evidence, and
  an inline operator-instruction block (Python diff + Alembic
  migration template + resume command). Picker:
  `Apply later (pause)` | `Decline and coerce` | `Abort`.
- **Pause / resume verification:** both the Python enum class
  (fresh import) and the DB CHECK constraint (via a new MCP tool
  `list_enum_values(table, column)`) must agree before a gap is
  recorded as `applied`. Reconciliation prompt handles the
  operator-renamed-the-value case.
- **Multi-gap detection** in one pass with an all-or-nothing pause
  picker; per-gap resume walk; one audit row per gap.
- **Audit trail:** schema deltas on the governance enums —
  `Action.suggest_enum_addition`, `TargetType.ENUM_VALUE`,
  `ValidationStatus.declined_by_operator`. Each gap produces its
  own `change_proposals` row with independent lifecycle (an enum
  widening, once committed, is real code regardless of the
  session's outcome).
- **Anti-laziness discipline:** three required conditions
  (no-existing-value-fits, catalog-impact, provider-evidence) plus
  per-proposal evidence structure plus an anti-pattern list plus
  drop-on-missing-evidence. Drafter does the same work either way;
  only the output differs between "real gap" and "documented
  coercion".
- **Decline-and-coerce:** audit row only, no automatic prose note
  in `series.name` or `series.description`. The coercion is the
  operator's curatorial decision; the catalog row reflects it and
  the audit row preserves the original judgment.
- **Operator UX:** template rendered inline at the wait node, no
  sandbox, no migration code generation. The ADR 0005 idiom is
  short and stable enough that inline templating beats a sandbox
  path.

Documentation updated:

- new ADR `docs/adr/0014-enum-gap-escalation.md`
- new skill `docs/skills/skill-enum-gap-escalation.md` at `draft`
- `CONTEXT.md` — new glossary entry for **Enum gap**
- `docs/series_onboarding_workflow.md` — new section
  `Enum-gap escalation`; `enum_gap_wait` added to node inventory;
  proposal-drafter role updated to remove structural enum fields
  from `suggest_human_apply` and route them through the gap flow
- inventory updates in `docs/adr/README.md` and
  `docs/skills/README.md`

No deferrals from this session; the parked thread is closed. A
follow-on column-gap escalation may surface eventually as its own
ADR-shaped discussion, but no such design is queued.

### [2026-06-10] Metadata standardisation design ratified as ADR 0013

Closed a `/grill-with-docs` session on how the gated onboarding agent's
proposal drafter handles prose fields (`description`, `name`, `variant`)
so the catalog gains consistent language across related series without
cosmetic churn on existing prose.

Decisions captured:

- new graph node `gather_reference_metadata` between `research` and
  `draft_proposal` retrieves three cohorts (sibling, cross-geography
  same-concept, same-provider same-concept via `series_sources`); empty
  cohorts are recorded explicitly; `is_first_in_family` is set when
  cohort A is empty
- new graph node `classify_extraction_mode` runs in parallel with
  `gather_reference_metadata` and writes the `extraction_mode` state
  field deterministically, replacing the drafter's earlier role of
  classifying inside its generative output
- per-field mutation matrix: agent mutates `series.name`, all
  `description` fields, and `variant` after Gate 1; `concept.name`,
  `series_family.name`, codes, and structural enum fields are
  propose-only and emitted with a new
  `change_proposal_item.action = suggest_human_apply`; executor skips
  these and they remain `pending_human_apply` until the operator marks
  them `applied_by_operator` in SQLAdmin
- scenario-2 (harmonisation updates to existing prose) routes through
  Gate 1 as companion items on the same proposal, not through Gate 2;
  Gate 2 retains its meaning as identity correction only
- proposed updates to existing prose require one of four closed
  triggers (`factual_incompleteness`, `factual_error`, `family_outlier`,
  `house_voice_outlier`) with asymmetric bars (factual cheap, style
  expensive); explicit anti-pattern list (synonym swaps, capitalisation,
  reorder, aesthetic, single-sibling disagreement, retroactive hard
  rules) blocks the common cosmetic-churn failure modes
- new skill `skill-metadata-standardisation` codifies the forward
  direction (anchor new prose on cohort) and the reactive direction
  (closed-trigger updates to existing prose), with conditional
  `Seed exemplars` loaded only when cohort A is empty; held at `draft`
  status until operator review of the seed exemplars

Documentation updated:

- new ADR `docs/adr/0013-metadata-standardisation.md`
- new skill `docs/skills/skill-metadata-standardisation.md` at `draft`
- `CONTEXT.md` — new glossary entry for **Prose field**
- `docs/series_onboarding_workflow.md` — updated proposal-drafter role,
  Gate 1 summary contents, node inventory; added a Metadata
  standardisation section
- inventory updates in `docs/adr/README.md` and `docs/skills/README.md`

Deferred to a separate `/grill-with-docs` session: enum-gap escalation
(how the agent handles structural fields whose vocabulary is currently
inexpressible, including the pause / human-edits-code / resume
mechanism). A handoff document for that session has been prepared.

### [2026-06-09] Issue 14 — Request-centric debug bootstrap smoke implemented

Rebuilt the developer bootstrap smoke around the request-level ingestion model
and canonical hierarchy model.

Completion notes:

- added `macrodb bootstrap debug-smoke --database {app|test}` as a minimal local
  initialization path for inspecting the redesigned ingestion stack
- the debug smoke creates one shared request-level `ingestion_feed`, two active
  `ingestion_feed_members`, one feed-level run, two member-level run outcomes,
  and two observations pointing to the exact member outcomes
- added a simple canonical hierarchy edge from `DEBUG_TOTAL_INDEX` to
  `DEBUG_COMPONENT_A_INDEX` so hierarchy inspection is part of the smoke path
- kept the FRED preset available as a curated import path, but no longer relies
  on it as the minimal request-centric developer smoke

Verification:

- `uv run pytest tests/test_debug_bootstrap.py -q` exited 0 with `2 passed`

### [2026-06-09] Issue 18 — Observation provenance moved to member-level outcomes

Moved ingested observation lineage from feed-level `ingestion_run_logs` to exact
member-level `ingestion_run_log_members`.

Completion notes:

- replaced `observations.ingestion_run_log_id` with nullable
  `observations.ingestion_run_log_member_id`
- added an Alembic migration that backfills existing one-member run provenance
  before dropping the old feed-level observation FK
- updated SQLAlchemy, Pydantic, FastAPI bulk observation writes, SQLAdmin, FRED
  latest-snapshot writes, and derived-observation conflict handling
- updated canonical schema docs, FK policy docs, architecture notes, and tests
  to keep ADR 0010's lineage model consistent

Verification:

- `uv run pytest tests/test_observations_routes.py::test_bulk_observations_records_member_level_ingestion_provenance -q`
  exited 0
- `uv run pytest tests/test_fred_bootstrap.py::test_fred_bootstrap_creates_curated_rows_and_run_logs -q`
  exited 0
- `uv run pytest tests/test_e2e.py::test_api_records_shared_feed_execution_with_member_outcomes -q`
  exited 0

### [2026-06-09] Issue 16 — Member-level ingestion run outcomes implemented

Implemented runtime audit support for member-level outcomes inside request-level
ingestion executions.

Completion notes:

- added `ingestion_run_log_members` as one outcome row per attempted
  `ingestion_feed_member` inside one feed-level `ingestion_run_log`
- enforced one member outcome per `(ingestion_run_log_id, ingestion_feed_member_id)`
  execution attempt
- exposed member outcomes through SQLAlchemy, Pydantic, FastAPI CRUD routes,
  SQLAdmin, Alembic, and the canonical ER source
- updated the FRED latest-snapshot runtime path so one-member feed executions
  record both the feed-level run and the member-level outcome, including
  zero-write rerun attempts
- kept the observation provenance move scoped as remaining planned work

Verification:

- `uv run pytest tests/test_e2e.py::test_api_records_shared_feed_execution_with_member_outcomes -q`
  exited 0
- `uv run pytest tests/test_constraints.py::test_ingestion_run_log_member_allows_only_one_outcome_per_member_attempt -q`
  exited 0
- `uv run pytest tests/test_fred_bootstrap.py -q` exited 0 with `4 passed`

### [2026-06-09] Issue 17 — Static request-level ingestion catalog implemented

Implemented the static catalog reshape for request-level ingestion feeds.

Completion notes:

- changed `ingestion_feeds` into request-level configuration rows, no longer
  owned by a single `series_source`
- added `ingestion_feed_members` as the attachment from feeds to
  `series_sources`, with selector metadata, active state, optional execution
  order, and a uniqueness rule allowing exactly one member per `series_source`
- relaxed `series_sources.external_code` to nullable, non-unique, best-effort
  metadata and added nullable `ref_url`
- updated ORM models, Alembic migration chain, Pydantic schemas, API CRUD
  routes, SQLAdmin views, FRED bootstrap scaffolding, canonical schema docs, and
  constraint/e2e tests together

Verification:

- `uv run pytest tests/test_e2e.py::test_api_catalog_supports_shared_ingestion_feed_members -q`
  exited 0
- `uv run pytest tests/test_constraints.py::test_series_source_external_code_is_not_unique_within_catalog tests/test_constraints.py::test_series_source_allows_nullable_external_code_and_ref_url tests/test_constraints.py::test_ingestion_feed_member_allows_only_one_member_per_series_source -q`
  exited 0
- `uv run pytest tests/test_fred_bootstrap.py -q` exited 0 with `4 passed`
- `uv run pytest -q` with `FRED_API_KEY` unset exited 0 with `80 passed`

### [2026-06-09] Issue 15 — Hierarchy enrichment governance documented

Updated onboarding and catalog governance so likely child-series additions,
weak provider locators, and routine refresh boundaries are handled deliberately.

Completion notes:

- documented additive hierarchy enrichment review in onboarding, including the
  same-concept default and the approval path for cross-concept proposals
- clarified that hierarchy edges connect real canonical series, do not create
  hidden placeholders, and require human review when they change structure
- flagged weak provider locators as review concerns even when nullable schema
  fields allow incomplete `series_sources` metadata
- clarified that routine FRED and post-bootstrap refreshes must not mutate
  `series_hierarchy_edges`; structural changes go through explicit onboarding
  or approved repair flows

Verification:

- docs-level regression coverage added for the Issue 15 governance acceptance
  criteria

### [2026-06-09] Issue 13 — Canonical series hierarchy edges implemented

Implemented same-concept canonical `series` hierarchy rows as real parent-child
edges between published `series` records.

Completion notes:

- added `series_hierarchy_edges` with `RESTRICT` FKs to real parent and child
  `series` rows, a parent-not-child CHECK, and a unique parent/child edge
- exposed hierarchy edges through SQLAlchemy, Pydantic, FastAPI, and SQLAdmin
- enforced same-concept hierarchy creation in the API by resolving each series
  through its `series_family_members` / `series_families` concept
- preserved parent observations as independent published values; hierarchy
  edges do not imply replacement by child aggregation
- updated the canonical ER source to V4 and recorded the new FK policy in ADR
  0008

Verification:

- `uv run pytest tests/test_series_hierarchy_routes.py -q` exited 0 with
  `4 passed`

### [2026-06-09] Issue 12 — Request-level ingestion architecture ratified

Recorded ADR 0010 for the request-level ingestion model and canonical series
hierarchy work.

Completion notes:

- defined `ingestion_feed` as a request-level execution unit rather than a row
  owned by one `series_source`
- introduced the planned `ingestion_feed_member` and
  `ingestion_run_log_member` roles for extraction contracts and member-level
  provenance
- documented that ingested observations should point to member-level run rows
  after the schema redesign
- reopened hierarchy work as canonical `series` hierarchy, with ragged depth,
  additive enrichment, stored parent observations, same-concept defaults, and no
  hidden canonical placeholder nodes
- updated the build plan so this is active planned work after Phase 13, not a
  deferred composition-tree idea

Verification:

- docs-level regression coverage added for the ADR and architecture-facing docs

### [2026-06-09] FRED runtime config wired to DB metadata + reset path added

Refined the FRED bootstrap so runtime endpoint and credential resolution now
align with the catalog metadata instead of being duplicated in Python defaults.

Completion notes:

- wired the FRED runtime to resolve `providers.credentials_ref` through
  settings as an env-secret handle, keeping secrets out of the database while
  letting the provider row declare which credential key to use
- normalized the seeded FRED provider metadata so `providers.base_url` is the
  provider root (`https://api.stlouisfed.org/fred`) and the feed stores the
  relative observations path (`/series/observations`)
- updated the FRED runner so observation requests are built from the feed row,
  and metadata requests are derived from that feed path instead of being
  hard-coded separately in the runner
- removed the duplicated `series_id` storage from feed `request_params`; the
  runtime now continues to use `series_sources.external_code` as the canonical
  provider-side series identifier
- added `macrodb bootstrap fred-us-macro --reset --confirm` so curated FRED
  bootstrap rows can be removed from either `app` or `test` after inspection,
  while intentionally preserving the shared seeded provider/provider-catalog
  baseline
- extended integration coverage to assert the DB-driven runtime config and the
  reset behavior end-to-end against the `macrodb_test` harness

Verification:

- `uv run ruff check src/macro_foundry/config.py src/macro_foundry/seed/data/providers.py src/macro_foundry/ingestion/providers/fred.py src/macro_foundry/ingestion/runners/fred_series.py src/macro_foundry/bootstrap/fred_us_macro.py src/macro_foundry/bootstrap/__init__.py src/macro_foundry/cli.py tests/test_fred_bootstrap.py`
  exited 0
- `uv run pytest tests/test_fred_bootstrap.py tests/test_seed.py tests/test_app_factory.py -q`
  exited 0 with `8 passed`

### [2026-06-09] Interactive series onboarding workflow documented

Documented the new gated workflow for onboarding sources and canonical series as
an interactive multi-agent process instead of a single autonomous import step.

Completion notes:

- added `docs/series_onboarding_workflow.md` to separate onboarding workflow
  design from `series.code` naming governance
- added `docs/series_onboarding_workflow_visualization.html` as a standalone
  visual map of the graph, gates, retries, and output artifact
- kept `docs/series_catalog_governance.md` focused on canonical identity,
  default variants, ambiguity handling for code creation, and correction
  discipline for published series
- added glossary support in `CONTEXT.md` for `publication boundary` and
  `default variant`
- recorded the normal path as researcher -> reviewer -> human gate -> executor,
  with reviewer-controlled retry loops capped at 3
- scoped the onboarding workflow to stop at a monitored initial test-database
  backfill plus human review of the test outcome
- noted `dev -> prod` promotion as a separate outer workflow to design later

Deviation note:

- this is workflow/governance design only; no LangGraph or MCP implementation
  has been added yet

Verification:

- documentation now exists in committed repo files and is ready to guide a
  later orchestration implementation

### [2026-06-09] Test-targeted app serving for SQLAdmin inspection

Added a runtime app-factory path so the FastAPI app and SQLAdmin can be pointed
at `macrodb_test` directly for inspection after running the FRED bootstrap.

Completion notes:

- added shared runtime database-target resolution in `src/macro_foundry/db/`
  so CLI workflows can target `app` or `test` consistently
- updated the app construction path so `create_app(database_url=...)` can mount
  the API and SQLAdmin against a non-default engine while overriding the shared
  `get_session` dependency to match
- extended `macrodb serve` with `--database {app|test}` so `macrodb_test` can
  be viewed in SQLAdmin without manually rewriting `MACRODB_APP_URL`
- added focused app-factory coverage to confirm the test-targeted app binds the
  overridden session dependency and SQLAdmin engine to `macrodb_test`

Verification:

- `uv run ruff check src/macro_foundry/backend/main.py src/macro_foundry/db/session.py src/macro_foundry/cli.py tests/test_app_factory.py tests/test_fred_bootstrap.py`
  exited 0
- `uv run pytest tests/test_fred_bootstrap.py tests/test_app_factory.py tests/test_seed.py -q`
  exited 0 with `7 passed`

### [2026-06-09] Series-code governance clarified for compound variants

Refined the catalog-governance guidance so edge-case sibling variants can be
distinguished without inventing new concepts or new families.

Completion notes:

- updated `docs/series_catalog_governance.md` to explicitly allow compound
  variant tokens inside the canonical code, using separated tokens such as
  `CORE_1P_HH` rather than compressed blobs
- documented the machine-parsing rule: parse the fixed suffix from the right,
  parse geography from the left, and resolve the longest known `concept.code`
  before treating the remainder as the variant slot
- clarified in `CONTEXT.md` that `series_family_members.variant` is intended as
  a human-readable family label and is sufficient for rare edge cases, but is
  not a normalized taxonomy surface for broad cross-series querying

### [2026-06-09] FRED bootstrap implementation — Complete

Implemented the first-pass curated FRED U.S. macro bootstrap as a separate
CLI flow targeting either the app or test database.

Completion notes:

- added `macrodb bootstrap fred-us-macro --database {app|test}` through a new
  bootstrap package and Typer subcommand rather than folding the work into
  `macrodb seed`
- added a committed FRED adapter and latest-snapshot import runner under
  `src/macro_foundry/ingestion/` that fetch FRED metadata + observations,
  derives provider-specific period bounds, applies overlap-window incremental
  reads, and writes ingestion run logs plus snapshot-vintage observations
- added curated preset orchestration that upserts the agreed concepts,
  families, raw series, derived YoY series, provider mappings, ingestion feeds,
  derivation inputs, and computation run logs
- added focused integration coverage in `tests/test_fred_bootstrap.py` for the
  first run, unchanged reruns, and reruns with changed/new data against the
  real `macrodb_test` harness using a fake FRED client
- updated runtime config/dependencies so the bootstrap can read `FRED_API_KEY`
  through `macro_foundry.config.settings` and use `httpx` as a declared runtime
  dependency

Verification:

- `uv run ruff check src/macro_foundry/bootstrap src/macro_foundry/ingestion tests/test_fred_bootstrap.py src/macro_foundry/cli.py src/macro_foundry/config.py`
  exited 0
- `uv run pytest tests/test_fred_bootstrap.py -q` exited 0 with `3 passed`
- `uv run python -c "from macro_foundry.cli import app; print(sorted({group.name for group in app.registered_groups}))"`
  printed `['bootstrap']`

### [2026-06-09] FRED bootstrap design documented

Documented the agreed first-pass stress-test design for a curated FRED preset
that will populate catalog rows, latest-snapshot observations, and derived YoY
series before any broader ingestion framework work begins.

Completion notes:

- added `docs/series_catalog_governance.md` to govern canonical `series.code`
  construction, concept-vs-family-vs-variant boundaries, and provider-code
  separation for future workers and agents
- added `docs/fred_bootstrap_plan.md` to capture the exact first-pass preset
  scope, runtime behavior, schedule metadata convention, latest-snapshot
  vintage policy, and implementation seams for the next agent session
- added a `snapshot vintage` glossary term to `CONTEXT.md` so latest-snapshot
  imports are distinguished from provider-native archival vintages

Deviation note:

- this is design and documentation work only; no ingestion or bootstrap code
  has been implemented yet

Verification:

- documentation now exists in committed repo files and is ready to be used as
  the handoff basis for the next implementation session

### [2026-06-08] Phase 12 — Complete

Phase 12 is now closed. The test harness and suite were expanded to match the
build-plan coverage:

- rewired `tests/conftest.py` so the session-scoped setup migrates and seeds
  `macrodb_test` once, while each individual test runs inside a rolled-back
  transaction boundary instead of truncating the database
- added the missing Phase 12 modules:
  `tests/test_migrations.py`, `tests/test_seed.py`,
  `tests/test_crud_generator.py`, `tests/test_constraints.py`,
  `tests/test_admin_auth.py`, and `tests/test_e2e.py`
- kept the existing series / observations / admin coverage green against the
  seeded baseline by making the route tests seed-aware and narrowing the admin
  auth assertions to the behaviors that matter

Verification:

- `uv run ruff check tests` exited 0
- `uv run pytest -q` exited 0 with `68 passed in 2.22s`

### [2026-06-08] Phase 8 — Complete

Phase 8 is now closed. The seed/CLI work is complete and the final verification
step was satisfied by running the seed command against the local database.

Completion notes:

- the curated seed data surface remains the same as previously documented:
  geographies, memberships, tags, default providers, and provider catalogs
- the dependency-ordered seed runners and CLI entrypoint remain in place with
  idempotent upsert behavior
- this resolves the last unfinished earlier phase after Phases 9-11 were
  completed out of order

Verification:

- per user confirmation on 2026-06-08, the project seed command was run
  successfully against the local database, so the Phase 8 verify step is now
  satisfied


### [2026-06-08] SQLAdmin hardening — filters + tab coverage + navigation cleanup

The SQLAdmin surface was hardened after the first real browser pass exposed a
runtime break in list-page filters:

- fixed the shared admin base so raw `column_filters` declarations are
  normalized into concrete SQLAdmin filter objects, which restores enum,
  boolean, date, and numeric filtering across the admin list pages
- added `tests/test_admin_auth.py` coverage for the full mounted admin surface,
  logging in and asserting that every registered `/admin/<identity>/list`
  route renders successfully against `macrodb_test`
- reorganized the admin sidebar around the domain layers already described in
  the project docs (`Core Curation`, `Provider Layer`, `Series Catalog`,
  `Observation Layer`, `Governance`) instead of leaving 19 flat tabs in one
  undifferentiated list
- added sensible default list ordering for operator-facing pages so catalog
  tables open alphabetically and log / observation / governance views open
  newest-first

Verification:

- `uv run ruff check src/macro_foundry/backend/admin tests/test_admin_auth.py`
  exited 0
- `uv run pytest tests/test_admin_auth.py -q` exited 0 with `20 passed`

### [2026-06-08] Environment naming — local dev/test + cloud prod

Clarified and partially implemented the physical database naming model without
changing the logical `macrodb` system name:

- local Docker now uses `macrodb_dev` for the working database and
  `macrodb_test` for the isolated test database
- cloud / Neon is documented as production-only for now, using one physical
  database named `macrodb_prod`
- the existing `MACRODB_OWNER_URL`, `MACRODB_APP_URL`, and `MACRODB_TEST_URL`
  config surface remains unchanged; only the physical DB names behind those URLs
  changed
- `.env.example`, local bootstrap defaults, and the local `.env.local` on this
  machine were updated to point at `macrodb_dev` instead of `macrodb`
- because the local Postgres named volume preserves physical databases, existing
  local users need a full local DB reset / volume recreation rather than a
  plain container restart to pick up the renamed local databases
- local Docker commands must use `docker compose --env-file .env.local ...`
  unless a real `.env` file is added, because Compose does not read `.env.local`
  automatically and will otherwise fall back to placeholder passwords

Follow-on documentation work:

- ADR 0009 records the environment-specific physical database naming decision
- ADR 0006 remains the source of truth for the two-role split itself; the new
  ADR supersedes only the older physical database naming examples

### [2026-06-08] Phase 10 — Complete (implemented out of order)

The hand-written API surface now covers the two Phase 10 hotspots:

- added `src/macro_foundry/backend/api/series.py` with explicit create/update
  handling for canonical series, including merged-state revalidation on PATCH,
  proactive duplicate-code detection, and a detail GET route that eager-loads
  geography plus attached tags
- added `src/macro_foundry/backend/api/observations.py` with filtered list
  reads plus `POST /observations/bulk`, which validates each row individually,
  rejects duplicate keys within a single request, checks referenced IDs before
  writing, and upserts on `(series_id, period_start, vintage_date)` conflicts
- extended the schema surface with `SeriesReadDetail`, observation-bulk result
  models, and router registration so the new endpoints are mounted under
  `/api/v1`
- added focused route coverage in `tests/conftest.py`,
  `tests/test_series_routes.py`, and `tests/test_observations_routes.py` using
  the real `macrodb_test` database with Alembic migrations applied

Deviation note:

- completed Phase 10 before finishing Phase 8 because the user asked to
  implement the hand-tuned routes directly; seed/CLI work remains in progress

Verification:

- `.uv-bootstrap/bin/uv run ruff check src/macro_foundry/backend/api/series.py
  src/macro_foundry/backend/api/observations.py src/macro_foundry/schemas/series.py
  src/macro_foundry/schemas/observation.py src/macro_foundry/schemas/__init__.py
  tests/conftest.py tests/test_series_routes.py tests/test_observations_routes.py`
  exited 0
- `.uv-bootstrap/bin/uv run pytest tests/test_series_routes.py
  tests/test_observations_routes.py` exited 0 with `8 passed`

### [2026-06-08] Phase 11 — Complete (implemented out of order)

SQLAdmin now exists as a mounted admin surface ahead of Phases 8-10 because its
documented dependency is only the Phase 5 model graph:

- added `src/macro_foundry/backend/admin/_base.py` with shared `BaseModelView`
  defaults, relationship-label helpers, and an admin-specific form converter so
  foreign-key selects render meaningful labels instead of model reprs
- added `src/macro_foundry/backend/admin/auth.py` with a single-user
  `BasicAuthBackend` wired to the existing `settings.admin.*` credentials and
  session secret
- added domain view modules under `src/macro_foundry/backend/admin/views/`
  covering all 19 V3 tables, including project-default form exclusions,
  relationship formatters, JSONB textarea widget overrides, and read-only admin
  treatment for append-only observations and run logs
- added `src/macro_foundry/backend/admin/register.py` and mounted SQLAdmin at
  `/admin` from `src/macro_foundry/backend/main.py`

Deviation note:

- completed Phase 11 before Phase 10 because the user asked to implement the
  admin surface directly, and Phase 11 depends only on the Phase 5 model graph

Verification:

- `.venv/bin/ruff check src/macro_foundry/backend/admin
  src/macro_foundry/backend/main.py` exited 0
- `.venv/bin/python -c "from macro_foundry.backend.main import app, admin;
  print('routes=', len(app.routes)); print('admin=', type(admin).__name__)"`
  printed `routes= 91` and `admin= Admin`
- an unsandboxed FastAPI `TestClient` smoke script loaded `/admin/login`,
  authenticated with the configured admin credentials, created a concept
  through `/admin/concept/create`, verified the row in Postgres, deleted the
  temporary concept, and printed `admin-smoke-ok`
- an unsandboxed follow-up smoke script inserted two temporary geographies,
  loaded `/admin/geography-membership/create`, confirmed the foreign-key select
  rendered a human-readable `CODE - Name` label, cleaned up the temporary rows,
  and printed `admin-fk-label-ok ...`

### [2026-06-08] Phase 9 — Complete (out of order ahead of Phase 8)

FastAPI entrypoint scaffolding and the thin CRUD layer now exist for the simple
tables:

- added `src/macro_foundry/backend/crud.py` with one generator covering list,
  get, create, patch, and delete routes
- added `src/macro_foundry/backend/deps.py` with bearer-token auth and the
  shared session dependency surface
- added one router module per simple table under `src/macro_foundry/backend/api/`
  and registered them centrally for `/api/v1`
- added `src/macro_foundry/backend/main.py` with the FastAPI app entrypoint and
  a minimal `/healthz` route
- taught the generator to handle simple equality filters and composite-key
  junction tables so `series_family_members` and `series_tags` do not need a
  separate routing pattern
- added `uvicorn` to the runtime dependencies so the documented app startup
  command is actually available

Deviation note:

- completed Phase 9 before Phase 8 because the user asked to start API work
  immediately; the seed data and CLI work remains in progress

Verification:

- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run ruff check src/macro_foundry/backend`
  exited 0
- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run python -c "from macro_foundry.backend.main import app; print(len(app.routes))"`
  printed `90`
- a live ASGI-backed smoke script against the local Postgres database completed
  list/create/filter/patch/delete on `/api/v1/concepts/` and printed
  `crud-smoke-ok`
- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run uvicorn macro_foundry.backend.main:app --host 127.0.0.1 --port 8001`
  started successfully, and `curl http://127.0.0.1:8001/healthz` returned
  `{"status":"ok"}`

### [2026-06-08] Phase 8 — Scope finalized before verification

Phase 8 implementation reached the point where the remaining step was only the
final seed-command verification. The scope clarifications captured in code and
docs were:

- expanded the seed scope beyond the original geography/tag baseline to include
  a curated default provider and provider-catalog seed set
- fixed the geography curation boundary to all ISO 3166-1 geographies, US
  states plus DC, Japan prefectures, and the 8 Japan `chiho` regions
- fixed the tag taxonomy to the normalized 7-category subject set used in
  `src/macro_foundry/seed/data/tags.py`
- fixed the provider naming convention for country-scoped official sources to
  use 3-letter geography prefixes in the canonical provider name (`USA FRED`,
  `HKG Census and Statistics Department`, `JPN e-Stat`)
- fixed the default membership policy to current memberships by default, with
  explicit historical EU change tracking for the last 20 years including Brexit
- added the explicit `AU` geography exception so the seeded G20 membership can
  match the current official composition
- deferred two follow-up items to a later V2-style pass rather than changing
  V3 mid-phase: a nullable provider→geography link and a scheduled checker for
  EU membership expansion/retraction drift

Verification at that checkpoint:

- `uv run python - <<'PY' ...` imported the Phase 8 seed data modules and
  printed the expected counts for countries, subnationals, memberships,
  providers, catalogs, and tags
- `uv run pytest -q tests/test_seed_data.py tests/test_schemas.py`
  exited 0 with `15 passed`

### [2026-06-08] Phase 7 — Complete

Pydantic schemas now cover the full V3 table surface:

- added `src/macro_foundry/schemas/` modules for concepts, geographies, tags,
  providers, series, observations, derived-series metadata, ingestion feeds,
  run logs, and governance
- implemented `Base` / `Create` / `Update` / `Read` variants for each table,
  plus detail read models where same-domain nested rows are useful
- added schema-side validators mirroring the Phase 5 cross-field constraints:
  subnational parent requirement, growth-series horizon requirement,
  currency-series currency-code requirement, and observation period bounds
- exported the public schema surface from `src/macro_foundry/schemas/__init__.py`
- added focused Phase 7 coverage in `tests/test_schemas.py`

Verification:

- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run ruff check src/macro_foundry/schemas tests/test_schemas.py`
  exited 0
- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run pytest tests/test_schemas.py`
  exited 0 with `7 passed`
- `/Users/leodai/Development/macro_foundry/.uv-bootstrap/bin/uv run python -c "... from macro_foundry.schemas import SeriesCreate ..."`
  printed `schemas-ok`

### [2026-06-08] Phase 6 — Complete

Alembic scaffolding and the initial migration chain now exist and verify cleanly:

- added `alembic.ini`, `alembic/env.py`, and `alembic/script.py.mako`, with
  Alembic bound to `MACRODB_OWNER_URL` rather than the app role
- generated and reviewed `alembic/versions/0001_initial_schema.py` from
  `Base.metadata`, covering all 19 V3 tables with named UNIQUE constraints,
  cross-column CHECK constraints, enum CHECK constraints, and explicit
  ADR-0008-aligned `ondelete` behavior
- added handwritten migration `alembic/versions/0002_latest_observations_view.py`
  to create and drop the `latest_observations` view via raw SQL
- corrected the shared enum helper during migration review so enum columns now
  persist enum values rather than member names, and emit real DB CHECK
  constraints via `create_constraint=True`

Verification:

- `.venv/bin/ruff check alembic src/macro_foundry/models/_schema_policy.py`
  exited 0
- `.venv/bin/python -c ...` confirmed `tables=19`, `Series.frequency` stores
  `['D', 'W', 'M', 'Q', 'S', 'A']`, and the enum type has
  `create_constraint=True`
- `.venv/bin/alembic upgrade head` succeeded against the local owner database
- `.venv/bin/alembic downgrade base && .venv/bin/alembic upgrade head`
  round-tripped cleanly
- a verification query after the round-trip confirmed 19 domain tables plus the
  `latest_observations` view in `public`

### [2026-06-08] Schema policy refactor — complete before Phase 6

Deepened the ORM graph's shared schema policy without starting Alembic work:

- added a private helper module at `src/macro_foundry/models/_schema_policy.py`
  with the two agreed seams only: `enum_column(...)` and `fk_uuid(...)`
- updated `docs/code_standards.md` to anchor the allowed helper boundary in
  writing before the refactor
- applied the seam across the repeated enum and non-PK UUID foreign-key shapes
  in the Phase 5 model graph
- kept composite-key junction structure local in model modules; the
  `series_tags` and `series_family_members` FK columns remain inline because
  `primary_key=True` is part of the local table structure rather than shared FK
  policy
- did not add relationship, CHECK, UNIQUE, scalar-column, or PK helpers

Verification:

- `.uv-bootstrap/bin/uv run ruff check src/macro_foundry/models` exited 0
- `.uv-bootstrap/bin/uv run python -c "from macro_foundry.models import *;
  print('imports-ok')"` printed `imports-ok`
- `.uv-bootstrap/bin/uv run python -c "from macro_foundry.models import *; from
  sqlalchemy.orm import configure_mappers; configure_mappers(); from
  macro_foundry.db.base import Base; print(f'tables={len(Base.metadata.tables)}')"`
  printed `tables=19`

### [2026-06-08] Documentation alignment — `CONTEXT.md` moved to repo root

Aligned markdown docs with the glossary move from `docs/CONTEXT.md` /
`docs/glossary.md` to the repo-root `CONTEXT.md`:

- updated `AGENTS.md` and `CLAUDE.md` so the required reading list and
  documentation-update rules point at `CONTEXT.md`
- updated `docs/architecture.md` and `docs/build_plan.md` so the documented repo
  layout matches the current file location
- updated `README.md` to list `CONTEXT.md` as a first-class project entrypoint

### [2026-06-08] Phase 5 — Complete

SQLAlchemy models now cover the full V3 schema surface:

- added model modules for geography, concepts, tags, providers, series,
  observations, derived-series metadata, ingestion feeds, run logs, and
  governance
- implemented the V3 cross-column CHECK constraints and the three one-to-one
  UNIQUE constraints called out in the build plan
- wired every foreign key with explicit ADR-0008-aligned `ondelete` behavior
  and exported the full model graph from `src/macro_foundry/models/__init__.py`
- kept `series_tags` and `series_family_members` schema-native instead of
  forcing synthetic IDs, because V3 defines them as composite-key tables
- corrected stale docs that said V3 had 18 tables; the canonical schema
  currently defines 19

Verification:

- `.uv-bootstrap/bin/uv run ruff check src/macro_foundry/models` exited 0
- `.uv-bootstrap/bin/uv run python -c "from macro_foundry.models import *; from
  macro_foundry.db.base import Base; print(len(Base.metadata.tables))"` printed
  `19`
- `.uv-bootstrap/bin/uv run python -c "from macro_foundry.models import *; from
  sqlalchemy.orm import configure_mappers; configure_mappers(); print('mappers-ok')"`
  printed `mappers-ok`

### [2026-06-08] Foreign-key deletion policy — ADR 0008

Resolved an ambiguity that blocked Phase 5 models and Phase 6 migration review:

- added ADR 0008 defining explicit `ON DELETE` behavior for every V3 foreign key
- updated the canonical schema relationships section so each FK now carries its
  delete policy inline
- updated the architecture and build plan so Phase 5/6 no longer assume an
  unstated deletion policy

### [2026-06-08] Phase 4 correction — removed mistaken tag enum placeholder

Corrected a Phase 4 artifact that contradicted ADR 0002:

- removed `src/macro_foundry/enums/tag.py`; it was an empty placeholder with no
  runtime callers
- updated the architecture and build plan so the enum package only covers
  code-routing and CHECK-constrained values
- made the tags exception explicit in current progress notes: tags are curated
  seed data, not Python enums

### [2026-06-08] Ingestion feed taxonomy — `file_upload` renamed to `file`

Refined `FeedMethod` so the enum describes acquisition mechanism rather than
operator workflow:

- renamed `file_upload` to `file` to cover uploads, watched paths, and other
  file-based ingestion paths
- added `scrape` as a distinct future ingestion method alongside `api` and
  `file`
- updated the glossary and canonical schema comments to match the broader
  ingestion-method vocabulary

### [2026-06-08] Geography taxonomy — Added `subnational_region`

Recorded a new ADR and updated the domain language for country-scoped grouping
geographies:

- added ADR 0007 defining `subnational_region` as a first-class geography type
  for country-scoped groupings such as Japan `chiho` and US `Midwest`
- clarified that `parent_geography_id` is the country anchor for both
  `subnational` and `subnational_region`
- clarified that subnational membership into subnational regions is modeled via
  `geography_memberships`, not a forced single tree
- updated the schema/build-plan references that previously treated
  `parent_geography_id` as subnational-only

### [2026-06-08] Phase 4 — Complete

Enum scaffolding landed for the full V3 schema surface:

- added domain enum modules under `src/macro_foundry/enums/` for geography,
  series, providers, derivations, run logs, and governance workflows
- re-exported the public enum surface from `src/macro_foundry/enums/__init__.py`
  so models and schemas can import from one stable package entrypoint
- kept tags out of the enum package because they are curated seed data rather
  than code-routing enums

Verification:

- `.uv-bootstrap/bin/uv run ruff check src/macro_foundry/enums` exited 0
- `.uv-bootstrap/bin/uv run python -c "from macro_foundry.enums import Frequency;
print(Frequency.MONTHLY.value)"` printed `M`

### [2026-06-08] Agent manual — Commit message guidance added

Updated `AGENTS.md` and `CLAUDE.md` with a shared commit-message standard:

- use a short `type(scope): subject` format when it improves clarity
- write for a developer who understands the domain but has not read the diff
- explain behavioral, schema, or architectural impact rather than listing files
- avoid vague subjects and patch-summary bodies

### [2026-06-08] Phase 3 — Complete

Core runtime scaffolding landed:

- added `src/macro_foundry/config.py` with a typed `Settings` object that reads
  `.env.local`, exposes `settings.db`, `settings.admin`, and `settings.api`,
  and configures the project logger
- added `src/macro_foundry/db/base.py` with the shared declarative `Base`,
  `TimestampedBase`, and `CreatedAtBase` mixins using server-side `uuidv7()`
  and timestamp defaults
- added `src/macro_foundry/db/session.py` with the async engine, async
  sessionmaker, and request-scoped `get_session()` dependency using the agreed
  Neon-safe pool settings and `expire_on_commit=False`
- updated `src/macro_foundry/db/__init__.py` exports to expose the shared DB
  primitives cleanly
- expanded `.env.example` with the API/admin/logging placeholders used by the
  new settings module
- populated the local gitignored `.env.local` from the example so Phase 3 can
  be verified end-to-end on this machine

Verification:

- `.uv-bootstrap/bin/uv run ruff check src/macro_foundry/config.py src/macro_foundry/db`
  exited 0
- `.uv-bootstrap/bin/uv run python ...` using `macro_foundry.db.session.async_engine`
  executed `SELECT 1` successfully against the local database

### [2026-06-08] Phase 2 — Complete

Docker and local Postgres bootstrap landed:

- added `docker-compose.yml` for a local `postgres:18.4` service with a
  persistent named volume, port 5432, and a healthcheck
- added `docker/postgres/init/01_roles.sql` to create `macrodb_owner` and
  `macrodb_app`, create `macrodb` and `macrodb_test`, and apply app-role grants
  plus default privileges in both DBs
- updated `.env.example` with `POSTGRES_PASSWORD` alongside the Phase 2 DB URLs

Verification:

- `docker compose config` exited 0
- `docker compose up -d --force-recreate` started a healthy Postgres 18.4
  container
- container logs confirmed `01_roles.sql` ran successfully on init
- role checks inside the container confirmed `macrodb_owner` and `macrodb_app`
  exist
- connection checks confirmed `macrodb_owner` can connect to `macrodb`,
  `macrodb_app` can connect to both `macrodb` and `macrodb_test`
- privilege boundary check confirmed `macrodb_app` cannot create tables in
  `public`

Deviation note:

- this host does not have `psql` installed on `PATH`, so verification used
  `docker compose exec ... psql ...` inside the running container
- Postgres 18 images expect the named volume mounted at `/var/lib/postgresql`,
  not `/var/lib/postgresql/data`; the compose file reflects that requirement

### [2026-06-08] Phase 1 — Complete

Repo skeleton aligned to `docs/architecture.md`:

- created `docs/`, `docs/adr/`, `docs/schema/`, `src/macro_foundry/`, `alembic/`,
  `docker/`, `tests/`, and `scripts/` scaffolding
- moved project docs under `docs/`
- moved ADRs under `docs/adr/`
- moved the canonical V3 schema to `docs/schema/db_er.txt`
- replaced the root `README.md` with a repo entrypoint and moved the ADR index
  content to `docs/adr/README.md`
- added `.gitignore`, `.env.example`, and a gitignored `.env.local`
- added `pyproject.toml` with the Phase 1 runtime and dev dependencies
- corrected the glossary-path references in `architecture.md` and
  `build_plan.md` to match the then-current repo layout
- generated `uv.lock` and the project `.venv`

Verification:

- `.uv-bootstrap/bin/uv sync` exited 0
- `.uv-bootstrap/bin/uv run python -c "import macro_foundry"` exited 0

Deviation note:

- this host did not have `uv` installed on `PATH`, so verification used a
  repo-local bootstrap venv at `.uv-bootstrap/` to provide the `uv` binary

### [2026-06-08] Phase 0 — Complete

Agent infrastructure laid down:

- `CLAUDE.md` and `AGENTS.md` at project root (identical content)
- `CONTEXT.md`, `docs/project_overview.md`, `docs/architecture.md`,
  `docs/code_standards.md`, `docs/build_plan.md`, `docs/progress_tracker.md`
- `docs/adr/0001-uuidv7-server-side-defaults.md` through
  `docs/adr/0006-two-role-architecture.md`

Pocock skills installed:

- `/grill-with-docs`
- `/tdd`
- `/diagnose`
- `/zoom-out`

V3 schema confirmed final at `docs/schema/db_er.txt`. Two enforcements
intentionally omitted (no `reference_kind → reference_year` CHECK, no
`series_family_members` partial unique). These are documented in `build_plan.md`
Phase 5 so they aren't silently re-added.

Decisions ratified in this session:

1. uuidv7 + timestamp defaults — server-side
2. CHECK constraints via Python enums (not native PG ENUM)
3. Thin in-repo CRUD generator + hand-tuned hotspots (not PostgREST, not Django,
   not SQLModel)
4. psycopg3 async (not asyncpg)
5. Seed via Typer CLI with `ON CONFLICT DO UPDATE` (not Alembic data migrations)
6. SQLAdmin with `BaseModelView` defaults + per-table overrides
7. ~28-test suite focused on generator + constraints + integration
8. Single bearer token API auth + basic-auth admin
9. Direct Neon endpoint (not pooled `-pooler`) with `pool_pre_ping` + `pool_recycle`
10. Hand-written Alembic migration for `latest_observations` view
11. Two-role split: `macrodb_owner` for migrations, `macrodb_app` for everything else

### [2026-06-10] Gated onboarding graph — design consolidation

Outcome of a two-session `/grill-with-docs` design pass for the
implementation of the gated onboarding workflow on top of the
request-level ingestion schema.

Updated:

- `docs/series_onboarding_workflow.md` — three reviewer specializations
  (governance, data correctness, selector code), explicit web-search and
  weirdness-detection duties on the researcher, script lifecycle section,
  approval-semantics section (A2 structured picker + free text), small-edit
  collision handling with Gate 2 escalation, executor split into
  `apply_catalog` / `trigger_first_run` / `monitor_first_run` for
  resumability, staging-not-test as the onboarding target, skill-loading
  trigger pattern, refreshed node inventory, refreshed implementation note
  covering LangGraph + Postgres checkpointer + `macrodb-mcp`
- `docs/adr/README.md` — index updated for ADR 0011 and 0012

New:

- `docs/environments.md` — purpose and lifecycle of `macrodb_dev`,
  `macrodb_test`, `macrodb_staging`, `macrodb_prod`; rationale for staging on
  Neon; agent process targeting rules
- `docs/adr/0011-gated-onboarding-graph.md` — chat-session topology,
  LangGraph + custom `macrodb-mcp`, role separation as code-level guarantee,
  per-role `RoleConfig`, `change_proposals.source_agent_session_id` link
- `docs/adr/0012-selector-registry-ingestion-runtime.md` — C4-honest
  selector library at `src/macro_foundry/ingestion/runtime/`,
  `selector_type` as unit of Python, sandbox/promote flow, FRED migration
- `src/macro_foundry/ingestion/runtime/README.md` — selector contract,
  decision rule for existing vs. new selectors, defensive parsing
  discipline, sandbox lifecycle
- `docs/skills/` — README plus eleven stub files for the v1 skill
  inventory; bodies deferred until the runtime can load them

Locked architectural decisions:

1. Chat-session CLI topology, no daemon, Postgres-checkpointer-backed
   pause/resume via `--resume <session-id>`.
2. LangGraph D2: structured graph with LLM-powered nodes and state-dependent
   conditional edges; not a single ReAct loop.
3. Checkpointer in a `langgraph` schema in the same Postgres DB as
   `macrodb`; `change_proposals.source_agent_session_id` links durable
   governance artifacts to the originating LangGraph thread.
4. Custom `macrodb-mcp` server (read-only and write-enabled instances) as the
   catalog seam; generic Postgres MCPs explicitly rejected.
5. Four logical databases: `dev`, `test` (pytest-only), `staging` (Neon,
   onboarding target), `prod` (Neon, separate promotion flow).
6. Skills as lazy-loaded Markdown packs under `docs/skills/`, state-triggered
   per LLM call; domain knowledge only, not procedural instructions.
7. C4-honest ingestion model: selector library at
   `src/macro_foundry/ingestion/runtime/` with `selector_type` extensions for
   gnarly providers; unit of Python is the selector, not the feed; FRED to be
   migrated off the current bespoke runner onto a generic `json_path`
   selector.
8. Three reviewer specializations replacing the single reviewer role.
9. A2 approval semantics: Questionary picker + free text; same model for
   Gate 1 and Gate 2; small textual edits skip full review with uniqueness
   pre-check and structured collision handling; un-approval allowed before
   commit.
10. Per-role LLM config (`RoleConfig`) in `src/macro_foundry/agent/roles.py`,
    with within-role tiering via `models_by_task` and a `task_hint` at call
    sites; v1 OpenAI-only.

Planned downstream: `/to-prd` for a PRD covering implementation of the
gated onboarding agent, then `/to-issues` to slice it into vertical
implementation tickets.

Deviation note:

- this is design and documentation work; no LangGraph, MCP, runtime, or
  agent code has been implemented yet

### [2026-06-12] Scoping subgraph refactor — three-node split

Restructured the onboarding scoping prototype in
`src/macro_foundry/onboarding_agent/1_scoping.ipynb` from a two-node graph
(`clarify_with_user` -> `write_series_brief`, with a back-edge where the brief
writer also voted on `needs_clarification`) into a three-node graph with
single-responsibility nodes:

```
START -> clarify_with_user -> verify_identifier -> write_series_brief -> END
              ^                       |
              |_______________________|
                (bounded retry, MAX_VERIFICATION_ATTEMPTS = 2)
```

Motivation: a user requesting "headline inflation FRED CPILFESL" passes the
clarifier (provider + ticker is unambiguous on its face) but `CPILFESL` is
core CPI, not headline. The old brief writer caught this only as a side
effect of authoring, which meant two prompts were voting on the same
`needs_clarification` decision with no shared definition.

Updated:

- `src/macro_foundry/onboarding_agent/1_scoping.ipynb` — cells `57f0bb17`
  (`%%writefile state_scope.py`) and `f9da056d`
  (`%%writefile onboarding_scope.py`) rewritten to match the new topology
- `src/macro_foundry/onboarding_agent/state_scope.py` (regenerated):
  - `AgentState` namespaced per node (`clarification_*`, `verification_*`,
    `series_brief`)
  - new `VerificationFindings` schema (canonical_name, source_url, notes) as
    a byproduct passed forward to the brief writer
  - new `VerifyIdentifier` schema (has_conflict, conflict_description,
    findings) for the verification node
  - `SeriesBrief` shrunk to a pure author output; the
    `needs_clarification` / `clarification_question` / `clarification_reasons`
    fields are removed
- `src/macro_foundry/onboarding_agent/onboarding_scope.py` (regenerated):
  - `clarify_with_user` now accepts a `verification_conflict` placeholder
    and constrains its question to that conflict when set
  - new `verify_identifier` node, web-verifies the identifier against the
    user's description, routes back to clarify on mismatch with bounded
    retries, otherwise proceeds to the brief writer
  - `write_series_brief` simplified to a pure author that reads
    `verification_findings` as authoritative and fills gaps via targeted
    `web_search`; no gating
- `src/macro_foundry/onboarding_agent/prompts.py`:
  - `clarify_with_user_instructions`: criteria 5 (acronym handling) and 6
    (identifier/description conflict) removed; new `<VerificationConflict>`
    block with an "if non-empty, ask only about this" branch; "out of scope"
    note that points conflict-detection to `verify_identifier`
  - new `verify_identifier_instructions` prompt with hard rules to keep it
    focused on conflict detection (findings are a byproduct, not a goal)
  - `transform_messages_into_series_brief_prompt`: trailing
    `needs_clarification` gating block removed; new
    `<VerificationFindings>` block with "treat as authoritative, do not
    redo verification" framing

New:

- `docs/adr/0018-scoping-three-node-split.md` — ADR documenting the SRP
  rationale, CPILFESL/headline failure case, loop bound, prompt-boundary
  rules, and alternatives considered (collapse, beefed-up clarifier,
  self-revise loop, no cap)
- `docs/adr/README.md` index updated for ADR 0018

Deviation note:

- this is prototype work in the `onboarding_agent/` notebook directory; it
  is upstream of the gated onboarding graph in ADR 0011 and does not yet
  touch the production `macrodb-mcp` seam or LangGraph checkpointer
- no test run was executed as part of this commit; verification cases
  (`FRED CPIAUCSL`, `headline inflation FRED CPILFESL`, `give me CPI`) are
  listed in the notebook for manual run by the developer

### [2026-06-13] MVP MCP-chat spike + ADR 0024 (agent↔macrodb-mcp connection lifecycle)

Done:

- added a throwaway spike to de-risk ADR 0019's core seam: a single
  `create_react_agent` node bound to the read-only `macrodb-mcp` tools,
  runnable on `langgraph dev` as the `macrodb_chat` graph
  - `src/macro_foundry/onboarding_agent/mcp_chat.py` (new)
  - `langgraph.json` registers `macrodb_chat`
  - deps: `langchain-mcp-adapters` (runtime), `langgraph-cli[inmem]` (dev)
  - committed `231e645`, labelled `test(agents):` — spike, not production
- verified end to end: the node spawns `macrodb serve mcp --target dev` over
  stdio, loads all 12 read tools, and runs a tool-calling chat loop

Findings:

- dev and test catalogs are **both empty** (0 concepts / families / series),
  so semantic `search_*` returns `[]`; the agent's earlier "rich" answer was
  a hallucination over empty results. Canonical bootstrap
  (`macrodb db bootstrap fred-us-macro --target dev`) has not been run; that
  path embeds-on-write via the registration helpers.
- read surface is semantic-search-only: there is no list/browse tool, so
  "what concepts do I have" has nothing to enumerate with — a real gap for
  human-facing chat, distinct from the `check_db` retrieval-from-prose use.
- `search_concepts("")` 400s at the embeddings API (empty-string input);
  should be guarded.

ADR 0024 (Proposed):

- `docs/adr/0024-agent-mcp-connection-lifecycle.md` — runtime nodes must
  reach `macrodb-mcp` over **one persistent session per graph run**, never
  `MultiServerMCPClient.get_tools()` over stdio (which re-spawns the server
  subprocess — new interpreter, engine, and Postgres pool — on every tool
  call). Transport stays stdio for now; `macrodb-mcp` as a streamable-HTTP
  service is noted as the expected prod direction but deliberately not
  decided here (narrow scope per user).
- `docs/adr/README.md` index updated for ADR 0024

### Issue #77 — V8 schema promoted to canonical (2026-06-20)

- replaced `docs/schema/db_er.txt` (V7) with the full V8 source from
  `docs/schema/db_er_proposed.txt`; header now reads "Schema V8 (category-tree
  collapse + provider source groups)"
- removed STATUS: PROPOSED note; canonical note ("this is the source of truth")
  inserted in its place
- `db_er_proposed.txt` kept as reference (unchanged)
- CLAUDE.md + AGENTS.md updated: V3 → V8 references in the schema section
- acceptance test added: `tests/test_schema_v8_canonical.sh` (13/13 PASS)
- no code or model changes; schema doc only (ADR 0025 + 0026 contract)

### [Future entries go above this line]
