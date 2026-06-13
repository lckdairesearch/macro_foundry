# ADR 0024 — Agent reaches macrodb-mcp over a persistent per-run session

**Status:** Proposed

**Date:** 2026-06-13

## Context

ADR 0011 fixes the *boundary*: an onboarding-agent node reaches the catalog
only through the `macrodb-mcp` server, never via raw SQL or a direct session.
It does not say *how* a graph node should connect across that boundary. That
gap matters more than it looks.

A spike (`onboarding_agent/mcp_chat.py`, the `macrodb_chat` graph) wired a
single `create_react_agent` node to `macrodb-mcp` to prove the seam. It used
the convenience path:

```python
client = MultiServerMCPClient({"macrodb": {"command": "uv",
    "args": ["run", "macrodb", "serve", "mcp", "--target", "dev"],
    "transport": "stdio"}})
tools = await client.get_tools()
```

Reading the installed adapter (`langchain_mcp_adapters` 0.3.0) shows the cost.
`MultiServerMCPClient.get_tools()` returns tools bound to a *connection config*,
not a live session — its own docstring states "a new session will be created
for each tool call." For a stdio server, "new session" means `stdio_client(...)`
spawns a **fresh subprocess**. So every single tool call cold-starts the whole
stack: a new `uv` env resolution, a new Python interpreter, a new SQLAlchemy
async engine, and a new Postgres connection pool, used for one query, then torn
down. The empty-catalog retry storm observed in the spike (seven `search_*`
calls) was seven full process + DB-engine cold starts.

This is invisible at the call site, contradicts the handoff's stated intent
("adds *a* subprocess at session start"), and is exactly the kind of thing that
gets copied into real nodes — including `check_db` (ADR 0019) — by default.

## Decision

For the **agent runtime** (every onboarding-graph node that calls `macrodb-mcp`,
`check_db` included), connect over **one persistent `macrodb-mcp` session,
reused for all tool calls within a graph run**. Bind tools from that live
session:

```python
async with client.session("macrodb") as session:
    tools = await load_mcp_tools(session)
    # one subprocess, one warm engine + pool, reused across all tool calls
```

Concretely:

- **Do not** use `MultiServerMCPClient.get_tools()` over stdio in runtime nodes.
  It is per-call by construction and re-spawns the server on every tool call.
- The session is opened once during graph/agent setup and held for the life of
  the run (or longer, if a node loop owns it), and closed on teardown. The node
  owns that lifecycle, including restarting the child if it dies.
- **Transport** for the persistent session stays **stdio** (one subprocess per
  run) for now. This is sufficient for a single agent runtime and keeps the
  ADR-0011 boundary intact.
- The **spike `macrodb_chat` graph is explicitly exempt** as throwaway
  scaffolding. It is not a template for runtime nodes and should not be promoted
  as one.

## Consequences

- One warm SQLAlchemy engine and connection pool per run instead of one per
  tool call. This protects Neon's connection budget under concurrent onboarding
  sessions — the per-call pattern's churn was the real scaling hazard.
- `check_db` (ADR 0019) builds directly on this: it binds the search +
  drill-down tools from the persistent session, and its 6-call cap reuses a
  single warm process rather than paying six cold starts.
- Node code now owns an async session lifetime. Under `langgraph dev` and the
  LangGraph runtime this means opening the session in graph setup/lifespan and
  closing it on shutdown, with handling for child-process death. This is more
  wiring than `get_tools()`, and that cost is accepted.
- The spike file remains useful only for exercising the seam by hand; anyone
  reading it must know it does not reflect the runtime connection rule.

## Alternatives considered

- **Per-call stdio via `get_tools()` (what the spike does).** Rejected for
  runtime: a process + DB-engine cold start on every tool call, Postgres
  connection churn, and startup failures that surface as opaque per-call errors
  rather than a clear "server down."
- **`macrodb-mcp` as a long-lived streamable-HTTP service, agent connects over
  the network.** This is the likely production shape: a separately deployable
  service with health checks, restart-on-crash, horizontal scaling, and a warm
  pool, with the boundary becoming a network hop instead of a subprocess. It is
  **deliberately not decided here** — recorded as the expected prod direction,
  to be ratified when deployment topology is in scope. The persistent-session
  rule above holds regardless of which transport that future decision picks.
- **Direct in-process `MacrodbReadTools`, bypassing MCP.** Rejected: violates
  ADR 0011's boundary.
