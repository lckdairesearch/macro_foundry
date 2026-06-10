"""Standalone macrodb MCP server entry point."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import typer
from mcp.server.fastmcp import FastMCP

from macro_foundry.config import settings
from macro_foundry.db.session import create_async_engine_for_url, create_session_factory
from macro_foundry.mcp.read_tools import (
    FindSiblingSeriesArgs,
    ListEnumValuesArgs,
    ListProviderSeriesForConceptArgs,
    ListSeriesForConceptArgs,
    LookupConceptArgs,
    LookupFamilyArgs,
    MacrodbReadTools,
    SelectorConfigValidationArgs,
    SelectorSchemaArgs,
)


READ_ONLY_TOOL_NAMES = {
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

WRITE_TOOL_NAMES = {
    "propose_create_series",
    "apply_approved_proposal",
    "trigger_feed_execution",
}

T = TypeVar("T")


def reject_write_tool(tool_name: str) -> None:
    """Reject write-tool registration on the read-only MCP instance."""

    if tool_name in WRITE_TOOL_NAMES:
        raise ValueError(
            f"{tool_name} write tools are not available on the read-only MCP server"
        )
    if tool_name not in READ_ONLY_TOOL_NAMES:
        raise ValueError(f"{tool_name} is not part of the read-only MCP tool surface")


def bind_read_tool(
    server: FastMCP,
    tool_name: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Bind one allowed read-only tool to the MCP server."""

    reject_write_tool(tool_name)
    return server.tool(name=tool_name)


def build_read_only_server(database_url: str) -> FastMCP:
    """Build a read-only macrodb MCP server bound to one database URL."""

    engine = create_async_engine_for_url(database_url)
    session_factory = create_session_factory(engine)
    server = FastMCP("macrodb-mcp")

    async def with_tools(callback: Callable[[MacrodbReadTools], Awaitable[T]]) -> T:
        async with session_factory() as session:
            return await callback(MacrodbReadTools(session))

    @bind_read_tool(server, "lookup_concept")
    async def lookup_concept(code: str) -> dict[str, Any] | None:
        result = await with_tools(
            lambda tools: tools.lookup_concept(LookupConceptArgs(code=code))
        )
        return None if result is None else result.model_dump(mode="json")

    @bind_read_tool(server, "lookup_family")
    async def lookup_family(code: str) -> dict[str, Any] | None:
        result = await with_tools(
            lambda tools: tools.lookup_family(LookupFamilyArgs(code=code))
        )
        return None if result is None else result.model_dump(mode="json")

    @bind_read_tool(server, "find_sibling_series")
    async def find_sibling_series(family_id: str) -> list[dict[str, Any]]:
        result = await with_tools(
            lambda tools: tools.find_sibling_series(
                FindSiblingSeriesArgs(family_id=family_id)
            ),
        )
        return [series.model_dump(mode="json") for series in result]

    @bind_read_tool(server, "list_series_for_concept")
    async def list_series_for_concept(concept_id: str) -> list[dict[str, Any]]:
        result = await with_tools(
            lambda tools: tools.list_series_for_concept(
                ListSeriesForConceptArgs(concept_id=concept_id)
            ),
        )
        return [series.model_dump(mode="json") for series in result]

    @bind_read_tool(server, "list_provider_series_for_concept")
    async def list_provider_series_for_concept(
        provider_id: str, concept_id: str
    ) -> list[dict[str, Any]]:
        result = await with_tools(
            lambda tools: tools.list_provider_series_for_concept(
                ListProviderSeriesForConceptArgs(
                    provider_id=provider_id,
                    concept_id=concept_id,
                ),
            ),
        )
        return [series.model_dump(mode="json") for series in result]

    @bind_read_tool(server, "list_selector_types")
    async def list_selector_types() -> list[str]:
        return await with_tools(lambda tools: tools.list_selector_types())

    @bind_read_tool(server, "get_selector_schema")
    async def get_selector_schema(selector_type: str) -> dict[str, Any]:
        return await with_tools(
            lambda tools: tools.get_selector_schema(
                SelectorSchemaArgs(selector_type=selector_type)
            )
        )

    @bind_read_tool(server, "validate_selector_config")
    async def validate_selector_config(
        selector_type: str,
        config: dict[str, Any],
        sample_payload: Any | None = None,
    ) -> dict[str, Any]:
        result = await with_tools(
            lambda tools: tools.validate_selector_config(
                SelectorConfigValidationArgs(
                    selector_type=selector_type,
                    config=config,
                    sample_payload=sample_payload,
                ),
            ),
        )
        return result.model_dump(mode="json")

    @bind_read_tool(server, "list_enum_values")
    async def list_enum_values(table: str, column: str) -> dict[str, Any]:
        result = await with_tools(
            lambda tools: tools.list_enum_values(
                ListEnumValuesArgs(table=table, column=column)
            )
        )
        return result.model_dump(mode="json")

    return server


app = typer.Typer(help="Run macrodb MCP servers.")


@app.command()
def read_only(
    database_url: str | None = typer.Option(
        None,
        "--database-url",
        help="Async SQLAlchemy database URL for this MCP process.",
    ),
) -> None:
    """Run the read-only macrodb MCP server over stdio."""

    build_read_only_server(database_url or settings.db.app_url).run(transport="stdio")


def main() -> None:
    """Console-script entry point."""

    app()


__all__ = [
    "READ_ONLY_TOOL_NAMES",
    "WRITE_TOOL_NAMES",
    "app",
    "bind_read_tool",
    "build_read_only_server",
    "main",
    "reject_write_tool",
]
