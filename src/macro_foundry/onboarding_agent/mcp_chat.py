"""MVP spike: a single chat node wired to the macrodb MCP server.

Purpose: prove the seam ADR 0019's `check_db` node will rely on — a LangGraph
node reaching the catalog *only* through the read-only `macrodb-mcp` server
(ADR 0011), binding its tools, and answering questions about the database in an
interactive chat.

This is NOT `check_db`. There is no verdict schema, no routing, no search-call
cap. It is a `create_react_agent` with the 12 read tools bound, so the
`langgraph dev` chat panel gives a back-and-forth conversation for free.

Run:
    uv run langgraph dev
then open the `macrodb_chat` graph and ask, e.g.
    "What concepts are in the database?"
    "Search for series about inflation."
"""

from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

SYSTEM_PROMPT = """You are a read-only assistant over the macro_foundry catalog.

You can answer questions about the database ONLY by calling the macrodb-mcp
read tools available to you. Never invent catalog contents. If a tool returns
nothing, say so plainly.

Useful tools:
- search_series — semantic search from a free-text query. Start here when the
  user describes something in prose. (Concept/indicator search and drill-down
  were retired with the V7 spine in ADR 0025.)
- list_enum_values(table, column) — allowed enum values.

Be concise. Show the user what you found, not how you searched."""


def _model():
    # Mirror the existing scoping graph's model config (see onboarding_scope.py).
    return init_chat_model(
        model="openai:gpt-5.1",
        temperature=1,
        use_responses_api=True,
        streaming=False,
    )


async def make_graph():
    """Async graph factory: spawn the macrodb MCP server, bind its tools, return a chat agent.

    `langgraph dev` calls this once at graph build. The MCP client launches
    `macrodb serve mcp --target dev` as a stdio subprocess and exposes its
    read tools as LangChain tools.
    """
    client = MultiServerMCPClient(
        {
            "macrodb": {
                "command": "uv",
                "args": ["run", "macrodb", "serve", "mcp", "--target", "dev"],
                "transport": "stdio",
            }
        }
    )
    tools = await client.get_tools()
    return create_react_agent(_model(), tools, prompt=SYSTEM_PROMPT)
