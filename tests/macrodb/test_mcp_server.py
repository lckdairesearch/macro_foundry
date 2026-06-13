"""Smoke coverage for the standalone macrodb MCP server binding."""

from __future__ import annotations

import pytest

from macro_foundry.mcp.server import (
    READ_ONLY_TOOL_NAMES,
    WRITE_TOOL_NAMES,
    build_read_only_server,
    build_write_enabled_server,
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
        "lookup_indicator",
        "find_sibling_series",
        "list_series_for_concept",
        "list_provider_series_for_concept",
        "search_concepts",
        "search_indicators",
        "search_series",
        "list_selector_types",
        "get_selector_schema",
        "validate_selector_config",
        "list_enum_values",
    }
    with pytest.raises(ValueError, match="write tools are not available"):
        reject_write_tool("apply_approved_proposal")


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_write_enabled_server_binds_read_and_write_tools() -> None:
    server = build_write_enabled_server(
        "postgresql+psycopg://app:secret@example.test/macrodb"
    )
    tools = await server.list_tools()
    tool_names = {tool.name for tool in tools}

    assert READ_ONLY_TOOL_NAMES <= tool_names
    assert WRITE_TOOL_NAMES <= tool_names
    assert tool_names == READ_ONLY_TOOL_NAMES | WRITE_TOOL_NAMES


@pytest.mark.asyncio
@pytest.mark.no_db
async def test_read_only_server_does_not_expose_write_tools() -> None:
    read_server = build_read_only_server(
        "postgresql+psycopg://app:secret@example.test/macrodb"
    )
    read_tools = {tool.name for tool in await read_server.list_tools()}
    assert read_tools.isdisjoint(WRITE_TOOL_NAMES)


@pytest.mark.no_db
def test_write_tool_names_are_complete() -> None:
    assert WRITE_TOOL_NAMES == {
        "propose_create_series",
        "apply_approved_proposal",
        "trigger_feed_execution",
        "record_suggest_human_apply",
        "record_enum_gap_proposal",
        "record_credential_gap_proposal",
        "mark_proposal_outcome",
    }
