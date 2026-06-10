"""Smoke coverage for the standalone macrodb MCP server binding."""

from __future__ import annotations

import pytest

from macro_foundry.mcp.server import (
    READ_ONLY_TOOL_NAMES,
    build_read_only_server,
    reject_write_tool,
)


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_read_only_server_binds_only_read_tools() -> None:
    server = build_read_only_server(
        "postgresql+psycopg://app:secret@example.test/macrodb"
    )
    tools = await server.list_tools()

    assert server.name == "macrodb-mcp"
    assert {tool.name for tool in tools} == READ_ONLY_TOOL_NAMES
    assert READ_ONLY_TOOL_NAMES == {
        "lookup_concept",
        "lookup_family",
        "find_sibling_series",
        "list_series_for_concept",
        "list_provider_series_for_concept",
        "list_selector_types",
        "get_selector_schema",
        "validate_selector_config",
        "list_enum_values",
    }
    with pytest.raises(ValueError, match="write tools are not available"):
        reject_write_tool("apply_approved_proposal")
