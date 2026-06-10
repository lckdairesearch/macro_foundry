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
from macro_foundry.mcp.write_tools import (
    ApplyApprovedProposalArgs,
    MacrodbWriteTools,
    MarkProposalOutcomeArgs,
    ProposeCreateSeriesArgs,
    RecordCredentialGapProposalArgs,
    RecordEnumGapProposalArgs,
    RecordSuggestHumanApplyArgs,
    TriggerFeedExecutionArgs,
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
    "record_suggest_human_apply",
    "record_enum_gap_proposal",
    "record_credential_gap_proposal",
    "mark_proposal_outcome",
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


def _register_read_tools(
    server: FastMCP,
    with_read: Callable[[Callable[[MacrodbReadTools], Awaitable[Any]]], Awaitable[Any]],
) -> None:
    """Register all read tools on a server instance."""

    @server.tool(name="lookup_concept")
    async def lookup_concept(code: str) -> dict[str, Any] | None:
        result = await with_read(
            lambda tools: tools.lookup_concept(LookupConceptArgs(code=code))
        )
        return None if result is None else result.model_dump(mode="json")

    @server.tool(name="lookup_family")
    async def lookup_family(code: str) -> dict[str, Any] | None:
        result = await with_read(
            lambda tools: tools.lookup_family(LookupFamilyArgs(code=code))
        )
        return None if result is None else result.model_dump(mode="json")

    @server.tool(name="find_sibling_series")
    async def find_sibling_series(family_id: str) -> list[dict[str, Any]]:
        result = await with_read(
            lambda tools: tools.find_sibling_series(
                FindSiblingSeriesArgs(family_id=family_id)
            ),
        )
        return [series.model_dump(mode="json") for series in result]

    @server.tool(name="list_series_for_concept")
    async def list_series_for_concept(concept_id: str) -> list[dict[str, Any]]:
        result = await with_read(
            lambda tools: tools.list_series_for_concept(
                ListSeriesForConceptArgs(concept_id=concept_id)
            ),
        )
        return [series.model_dump(mode="json") for series in result]

    @server.tool(name="list_provider_series_for_concept")
    async def list_provider_series_for_concept(
        provider_id: str, concept_id: str
    ) -> list[dict[str, Any]]:
        result = await with_read(
            lambda tools: tools.list_provider_series_for_concept(
                ListProviderSeriesForConceptArgs(
                    provider_id=provider_id,
                    concept_id=concept_id,
                ),
            ),
        )
        return [series.model_dump(mode="json") for series in result]

    @server.tool(name="list_selector_types")
    async def list_selector_types() -> list[str]:
        return await with_read(lambda tools: tools.list_selector_types())

    @server.tool(name="get_selector_schema")
    async def get_selector_schema(selector_type: str) -> dict[str, Any]:
        return await with_read(
            lambda tools: tools.get_selector_schema(
                SelectorSchemaArgs(selector_type=selector_type)
            )
        )

    @server.tool(name="validate_selector_config")
    async def validate_selector_config(
        selector_type: str,
        config: dict[str, Any],
        sample_payload: Any | None = None,
    ) -> dict[str, Any]:
        result = await with_read(
            lambda tools: tools.validate_selector_config(
                SelectorConfigValidationArgs(
                    selector_type=selector_type,
                    config=config,
                    sample_payload=sample_payload,
                ),
            ),
        )
        return result.model_dump(mode="json")

    @server.tool(name="list_enum_values")
    async def list_enum_values(table: str, column: str) -> dict[str, Any]:
        result = await with_read(
            lambda tools: tools.list_enum_values(
                ListEnumValuesArgs(table=table, column=column)
            )
        )
        return result.model_dump(mode="json")


def build_read_only_server(database_url: str) -> FastMCP:
    """Build a read-only macrodb MCP server bound to one database URL."""

    engine = create_async_engine_for_url(database_url)
    session_factory = create_session_factory(engine)
    server = FastMCP("macrodb-mcp")

    async def with_read(callback: Callable[[MacrodbReadTools], Awaitable[T]]) -> T:
        async with session_factory() as session:
            return await callback(MacrodbReadTools(session))

    _register_read_tools(server, with_read)
    return server


def _register_write_tools(
    server: FastMCP,
    with_write: Callable[[Callable[[MacrodbWriteTools], Awaitable[Any]]], Awaitable[Any]],
) -> None:
    """Register all write tools on a server instance."""

    @server.tool(name="propose_create_series")
    async def propose_create_series(
        session_id: str,
        payload: dict[str, Any],
        rationale: str | None = None,
    ) -> dict[str, Any]:
        return await with_write(
            lambda tools: tools.propose_create_series(
                ProposeCreateSeriesArgs(
                    session_id=session_id,
                    payload=payload,
                    rationale=rationale,
                )
            )
        )

    @server.tool(name="apply_approved_proposal")
    async def apply_approved_proposal(approved_proposal_id: str) -> dict[str, Any]:
        return await with_write(
            lambda tools: tools.apply_approved_proposal(
                ApplyApprovedProposalArgs(approved_proposal_id=approved_proposal_id)
            )
        )

    @server.tool(name="trigger_feed_execution")
    async def trigger_feed_execution(feed_id: str) -> dict[str, Any]:
        return await with_write(
            lambda tools: tools.trigger_feed_execution(
                TriggerFeedExecutionArgs(feed_id=feed_id)
            )
        )

    @server.tool(name="record_suggest_human_apply")
    async def record_suggest_human_apply(
        items: list[dict[str, Any]],
        session_id: str,
        proposal_id: str | None = None,
    ) -> dict[str, Any]:
        from uuid import UUID as _UUID

        return await with_write(
            lambda tools: tools.record_suggest_human_apply(
                RecordSuggestHumanApplyArgs(
                    items=items,
                    session_id=session_id,
                    proposal_id=_UUID(proposal_id) if proposal_id else None,
                )
            )
        )

    @server.tool(name="record_enum_gap_proposal")
    async def record_enum_gap_proposal(
        gap: dict[str, Any],
        session_id: str,
    ) -> dict[str, Any]:
        return await with_write(
            lambda tools: tools.record_enum_gap_proposal(
                RecordEnumGapProposalArgs(gap=gap, session_id=session_id)
            )
        )

    @server.tool(name="record_credential_gap_proposal")
    async def record_credential_gap_proposal(
        gap: dict[str, Any],
        session_id: str,
    ) -> dict[str, Any]:
        return await with_write(
            lambda tools: tools.record_credential_gap_proposal(
                RecordCredentialGapProposalArgs(gap=gap, session_id=session_id)
            )
        )

    @server.tool(name="mark_proposal_outcome")
    async def mark_proposal_outcome(
        proposal_id: str,
        status: str,
        applied_value: str | None = None,
        rationale: str | None = None,
        applied_by: str | None = None,
    ) -> dict[str, Any]:
        from uuid import UUID as _UUID

        return await with_write(
            lambda tools: tools.mark_proposal_outcome(
                MarkProposalOutcomeArgs(
                    proposal_id=_UUID(proposal_id),
                    status=status,
                    applied_value=applied_value,
                    rationale=rationale,
                    applied_by=applied_by,
                )
            )
        )


def build_write_enabled_server(database_url: str) -> FastMCP:
    """Build a write-enabled macrodb MCP server bound to one database URL."""

    engine = create_async_engine_for_url(database_url)
    session_factory = create_session_factory(engine)
    server = FastMCP("macrodb-mcp-write")

    async def with_read(callback: Callable[[MacrodbReadTools], Awaitable[T]]) -> T:
        async with session_factory() as session:
            return await callback(MacrodbReadTools(session))

    async def with_write(callback: Callable[[MacrodbWriteTools], Awaitable[T]]) -> T:
        async with session_factory() as session:
            result = await callback(MacrodbWriteTools(session))
            await session.commit()
            return result

    _register_read_tools(server, with_read)
    _register_write_tools(server, with_write)
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


@app.command()
def write_enabled(
    database_url: str | None = typer.Option(
        None,
        "--database-url",
        help="Async SQLAlchemy database URL for this MCP process.",
    ),
) -> None:
    """Run the write-enabled macrodb MCP server over stdio."""

    build_write_enabled_server(database_url or settings.db.app_url).run(transport="stdio")


def main() -> None:
    """Console-script entry point."""

    app()


__all__ = [
    "READ_ONLY_TOOL_NAMES",
    "WRITE_TOOL_NAMES",
    "app",
    "bind_read_tool",
    "build_read_only_server",
    "build_write_enabled_server",
    "main",
    "reject_write_tool",
]
