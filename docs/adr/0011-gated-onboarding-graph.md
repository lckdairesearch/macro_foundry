# ADR 0011 - Gated onboarding graph implemented as a chat-session LangGraph agent

**Status:** Accepted

**Date:** 2026-06-10

## Context

`docs/series_onboarding_workflow.md` defines the gated workflow for onboarding
new sources and canonical series. It describes researcher / reviewer / executor
roles, two human approval gates, structural rules for hierarchy enrichment, and
the deferred boundary at which a test-approved onboarding package hands off to
a later deployment workflow.

The workflow document was deliberately implementation-agnostic. With the
request-level ingestion schema landed (issues 12, 13, 15, 16, 17, 18) and
ADR 0010 ratified, macrodb is ready to implement the workflow as actual
orchestration. That orchestration must:

- support a chat-style interaction model where the agent decides when to grill
  the operator versus when to proceed, rather than rendering a fixed wizard
- survive operator pauses and process exits without keeping background compute
  running, because the operator is a single developer working from a laptop
- keep the workflow doc's role separations and gate invariants as real
  code-level guarantees rather than as prompt discipline
- be portable from CLI to a future web frontend without rewriting the agent
  internals
- reach macrodb through a context-efficient, semantic seam rather than raw SQL
  or generic CRUD calls
- support eval and observability of LLM behavior over time, including when
  models or providers are swapped

The workflow also requires that catalog mutations land in a durable pre-prod
environment, not in the pytest-only `macrodb_test` database; `docs/environments.md`
formalizes this with a separate `macrodb_staging` target on Neon.

## Decision

The gated onboarding workflow is implemented as a LangGraph state machine
driven by a chat-style Typer CLI session, with a custom Model Context Protocol
server as the catalog seam.

**Process topology.** The CLI runs as a foreground process. `macrodb onboard`
opens a new chat session. `macrodb onboard --resume <session-id>` reopens a
saved session by reading from a LangGraph checkpointer and replaying the
transcript. The process exits cleanly on operator save or close; there is no
daemon, no background watcher, and no idle compute between sessions.
`--target {dev,staging}` selects the environment; `--target prod` is rejected
at argument parsing.

**Graph shape.** The LangGraph is a structured state machine with LLM-powered
nodes and state-dependent conditional edges, not a single ReAct loop. Roles
defined by the workflow doc map to graph structure, not to prompt discipline.
The read-only reviewer cannot reach a write tool because the write tool is not
bound to the reviewer's node; the executor cannot run before a human-approved
flag is present in the state.

**State persistence.** Graph state is persisted via LangGraph's `PostgresSaver`
into a `langgraph` schema within the same Postgres database that hosts
`macrodb`. The `langgraph` schema is owned by `macrodb_owner` and read/written
by `macrodb_app`. The application schema (`public`) and the agent state schema
(`langgraph`) are kept separate; graph state is conversational and ephemeral
by intent, even though retention is currently "forever for now" to support
eval work.

Durable governance artifacts live in `public.change_proposals` as before. A
new column `change_proposals.source_agent_session_id` references the
originating LangGraph `thread_id`, giving bidirectional traceability between
the conversation and the approved change set without merging the two storage
models.

**Catalog seam.** Agents reach macrodb only through a custom `macrodb-mcp`
server with a narrow, semantic tool surface (`lookup_concept`,
`lookup_family`, `find_sibling_series`, `propose_create_series`,
`apply_approved_proposal`, `list_selector_types`, `get_selector_schema`,
`validate_selector_config`, `trigger_feed_execution`, etc.). Read-only and
write-enabled instances are served from the same codebase but bind different
tool subsets. The MCP server is process-agnostic with respect to environment:
the same binary serves any database, connected by a different connection
string.

**Role configuration.** LLM configuration is per-role, expressed as typed
`RoleConfig` objects in `src/macro_foundry/agent/roles.py`. Roles are
researcher, proposal drafter, script drafter, validator, governance reviewer,
data correctness reviewer, selector reviewer, approval parser, test reviewer,
and dangerous correction planner. Within-role tiering is expressed via the
role's `models_by_task` map and a `task_hint` at the call site. v1 binds all
roles to OpenAI; the abstraction is structural so other providers can be
swapped in without code changes to nodes.

**Skill loading.** Domain knowledge lives in narrow Markdown skills under
`docs/skills/`. Each node declares a `skill_triggers` map of
`(state_predicate, skill_id)` pairs and assembles its prompt as
`base_role_prompt + selected_skill_bodies` per LLM call. Skills are domain
knowledge, not procedural instructions.

**Approval semantics.** Gate 1 and Gate 2 both use a structured Questionary
picker (`Approve`, `Reject`, `Request changes`) rendered beneath the proposal
summary, with free-text input available alongside. The structural picker
decides routing; an LLM only does extraction inside the `Request changes`
branch. Small textual edits run a uniqueness pre-check on touched UNIQUE
columns; collisions route to a structured three-way choice that includes
escalation into the Gate 2 dangerous-correction branch. Un-approval is allowed
in the armed-but-not-applied window.

**Reviewers.** The single "reviewer" role from the workflow doc is split into
three specializations that run in parallel after drafting and validation:
governance, data correctness, and selector code. Findings merge into one
review bundle before Gate 1.

**Onboarding target.** Onboarding sessions write to `macrodb_staging` by
default. The pytest-only `macrodb_test` database is never an onboarding target.

## Consequences

**Positive:**

- Pause and resume work without operator-managed background processes. Closing
  the laptop mid-session is safe; reopening with `--resume` reconstructs the
  full chat history and graph state from the checkpointer.
- The workflow doc's safety properties become structural code-level
  guarantees: reviewers cannot mutate because they cannot reach write tools;
  the executor cannot run before an approval flag is set in state; the
  3-cycle review cap is enforced by router code, not by prompt phrasing.
- A future web frontend reuses the same graph and MCP server with a different
  I/O channel implementation. The chat CLI is one client; a FastAPI/websocket
  surface can be a second client without changing agent internals.
- Per-role LLM configuration with per-call task hints lets cheaper models
  handle quick classification while reserving expensive reasoning models for
  the work that needs them, even within a single role's invocations.
- Skills give the agent only the domain context it currently needs. The
  researcher does not carry hierarchy-enrichment context when it is not
  evaluating a hierarchy edge.
- The link from `change_proposals.source_agent_session_id` to the LangGraph
  thread makes every durable governance row traceable back to the
  conversation that produced it without entangling the two storage models.
- Eval-friendly: `raw_messages` (with reasoning streams for thinking models),
  `node_transitions`, `llm_calls`, and `loaded_skills` are all append-only in
  state, so behavior can be analyzed after the fact and replayed against
  alternate models.

**Negative:**

- Adds three new build axes that did not exist before: the LangGraph state
  machine, the custom MCP server, and the chat CLI shell. None can be skipped;
  each is load-bearing.
- The `langgraph` checkpointer schema must be managed alongside the
  application schema, including its own migration story when LangGraph
  versions change.
- Large LLM message bodies and reasoning streams will accumulate in Postgres
  JSONB. Externalization to R2 for payloads above a threshold is required to
  keep checkpoint size bounded; the cutoff and the prune-after switch are
  implementation choices left to the build slice.
- A custom MCP server is more upfront work than reusing the existing FastAPI
  surface. The investment is justified by the context-efficiency win against
  LLM consumers, but it does push some validation logic into a second seam
  that must stay aligned with the Pydantic schemas.
- Per-role LLM config in Python is type-checked but requires code changes to
  swap roles to a different provider; the only operator-facing override
  surface is the `--<role>-model` CLI flags.

## Alternatives considered

- **Daemon-backed agent service with REST/websocket clients.** Rejected for
  v1 because a single-operator project does not justify managing a daemon
  lifecycle. The intent-object channel abstraction preserves the option of
  swapping to a daemon later without touching agent internals.
- **Ephemeral CLI per step (`start`, `continue`, `approve` as separate
  commands).** Rejected because the live monitoring of the first ingestion
  run becomes awkward without a continuous process to watch the run, and
  because chat-style interaction reads worse as a sequence of one-shot
  commands.
- **Single ReAct-style agent with tool calls including ask_user.** Rejected
  because the workflow doc's role separation, read-only reviewer rule, and
  cycle cap become soft prompt discipline rather than hard graph guarantees.
  Refactoring a single system prompt risks re-litigating safety properties
  every time.
- **SQLite checkpointer at `~/.macro_foundry/agent_state.db`.** Rejected
  because Postgres + JSONB handles the document-style state shape natively
  and reusing the existing Postgres stack keeps infrastructure tight. The
  `langgraph` schema isolation gives us the cleanliness benefits without
  introducing a second persistence engine.
- **Generic Postgres MCP servers exposing raw SQL.** Rejected because the
  LLM having to write SQL against the schema is the wrong abstraction:
  context cost is high, validation is absent, and the read/write boundary
  cannot be enforced server-side. A custom domain-level MCP solves all three.
- **Folding agent session state into `change_proposals`.** Rejected because
  the two have different lifecycles, schemas, and authorities.
  `change_proposals` is the canonical record of approved changes;
  checkpoint state is the conversational scratch space leading up to that
  approval. Linking them via a foreign key preserves both contracts.
- **YAML/TOML role configuration.** Rejected because role configs bind
  Python objects (skills, MCP tool sets, decode params) and string-typed
  indirection costs more in runtime errors than it saves in operator
  flexibility. CLI flags handle the small set of values an operator might
  flip per session.
- **A single reviewer role.** Rejected because governance fit, data
  correctness, and selector code review are different specialties with
  different skill sets and different appropriate model tiers. Forcing them
  into one prompt risks underweighting whichever specialty did not happen to
  drive the prompt's design.
- **Onboarding sessions writing to `macrodb_test`.** Rejected because
  pytest's reset-on-demand lifecycle is incompatible with multi-day
  onboarding work; see `docs/environments.md` for the
  `macrodb_staging`-on-Neon rationale.
