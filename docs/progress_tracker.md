# Progress Tracker

This file is the living record of what's been done. Update it when a phase
completes, when something deviates from the build plan, or when a handoff
between sessions happens.

Format per entry: `[YYYY-MM-DD] Phase N — Status. Notes.`

Most recent at the top.

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

### [Future entries go above this line]
