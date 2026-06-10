"""Production dependency factory for the onboarding agent.

Builds a complete OnboardingGraphDependencies from real backends so the CLI
path no longer falls back to _missing_graph_dependencies().
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import questionary

import openai
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.agent.llm_openai import (
    make_openai_llm_callable,
    make_openai_reviewer_callable,
)
from macro_foundry.agent.llm_schemas import (
    DraftOutput,
    ExtractionModeOutput,
    ResearchOutput,
    ReviewerOutput,
    TestReviewOutput,
)
from macro_foundry.agent.onboarding import OnboardingGraphDependencies
from macro_foundry.agent.roles import AgentRole, RoleConfig
from macro_foundry.agent.skills import SkillRegistry
from macro_foundry.mcp.read_tools import (
    FindSiblingSeriesArgs,
    ListProviderSeriesForConceptArgs,
    ListSeriesForConceptArgs,
    MacrodbReadTools,
    SelectorSchemaArgs,
)

_SKILLS_DIR = Path(__file__).resolve().parents[3] / "docs" / "skills"

_CUSTOM_PYTHON_KEYWORDS: frozenset[str] = frozenset(
    {"python", "script", "custom", "sdk", "client", "parse", "scrape"}
)


async def _questionary_picker(options: list[str], *_args: Any) -> str:
    """Questionary-backed picker; presents an interactive select prompt."""
    return await questionary.select("Select:", choices=options).unsafe_ask_async()


def _make_extraction_mode_classifier(
    *,
    session: AsyncSession,
    ambiguous_classifier: Callable[[list[dict[str, str]]], Awaitable[dict[str, Any]]] | None = None,
) -> Callable[[str], Awaitable[str]]:
    read_tools = MacrodbReadTools(session)

    async def _classify_extraction_mode(source_summary: str) -> str:
        lower = source_summary.lower()
        selector_types = await read_tools.list_selector_types()
        selector_schemas = {
            selector_type: await read_tools.get_selector_schema(
                SelectorSchemaArgs(selector_type=selector_type)
            )
            for selector_type in selector_types
        }
        if _matches_registered_selector(lower, selector_types, selector_schemas):
            return "config_only"
        if any(kw in lower for kw in _CUSTOM_PYTHON_KEYWORDS):
            return "custom_python"
        if ambiguous_classifier is not None:
            result = await ambiguous_classifier(
                [
                    {
                        "role": "user",
                        "content": (
                            "Classify whether this provider extraction can use an existing "
                            "selector configuration or needs custom Python.\n"
                            f"source_summary: {source_summary}\n"
                            f"selector_schemas: {json.dumps(selector_schemas, sort_keys=True)}"
                        ),
                    }
                ]
            )
            mode = result.get("extraction_mode")
            if mode in {"config_only", "custom_python"}:
                return str(mode)
        return "config_only"

    return _classify_extraction_mode


def _matches_registered_selector(
    source_summary: str,
    selector_types: list[str],
    selector_schemas: dict[str, dict[str, Any]],
) -> bool:
    for selector_type in selector_types:
        selector_phrase = selector_type.lower().replace("_", " ")
        selector_token = selector_type.lower()
        if selector_token in source_summary or selector_phrase in source_summary:
            return True
        if _matches_selector_schema(source_summary, selector_schemas.get(selector_type, {})):
            return True

    registry_shape_terms = {
        "json_path": (
            "records_path",
            "period_anchor_field",
            "value_field",
            "json array",
            "json api",
            "record path",
        ),
        "csv_column": ("period_column", "value_column", "csv column"),
        "estat_value_filter": ("e-stat", "estat"),
        "censtatd_json": ("censtatd", "census and statistics department"),
    }
    for selector_type in selector_types:
        for term in registry_shape_terms.get(selector_type, ()):
            if term in source_summary:
                return True
    return False


def _matches_selector_schema(source_summary: str, schema: dict[str, Any]) -> bool:
    required_fields = schema.get("required")
    if not isinstance(required_fields, list):
        return False
    matched = 0
    for field in required_fields:
        phrase = str(field).lower().replace("_", " ")
        if phrase in source_summary:
            matched += 1
            continue
        meaningful_tokens = [
            token
            for token in phrase.split()
            if token not in {"field", "fields", "path", "column", "columns"}
        ]
        if meaningful_tokens and all(token in source_summary for token in meaningful_tokens):
            matched += 1
    return matched >= 2


def _make_cohort_lookup(
    *,
    session: AsyncSession,
) -> Callable[[list[dict[str, Any]]], Awaitable[dict[str, Any]]]:
    read_tools = MacrodbReadTools(session)

    async def _cohort_lookup(catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        cohort_a: list[dict[str, Any]] = []
        cohort_b: list[dict[str, Any]] = []
        cohort_c: list[dict[str, Any]] = []
        family_ids: list[Any] = []
        concept_ids: list[Any] = []
        provider_ids: list[Any] = []

        for hit in catalog_hits:
            family_id = _first_present(hit, "family_id", "series_family_id")
            concept_id = _first_present(hit, "concept_id")
            provider_id = _first_present(hit, "provider_id")
            kind = str(hit.get("kind") or "").lower()
            entity_id = hit.get("id")

            if family_id is not None:
                family_ids.append(family_id)
            elif kind in {"family", "series_family"} and entity_id is not None:
                family_ids.append(entity_id)

            if concept_id is not None:
                concept_ids.append(concept_id)
            elif kind == "concept" and entity_id is not None:
                concept_ids.append(entity_id)

            if provider_id is not None:
                provider_ids.append(provider_id)
            elif kind == "provider" and entity_id is not None:
                provider_ids.append(entity_id)

        for family_id in _dedupe_values(family_ids):
            siblings = await read_tools.find_sibling_series(
                FindSiblingSeriesArgs(family_id=family_id)
            )
            cohort_a.extend(_dump_tool_rows(siblings))

        for concept_id in _dedupe_values(concept_ids):
            concept_series = await read_tools.list_series_for_concept(
                ListSeriesForConceptArgs(concept_id=concept_id)
            )
            cohort_b.extend(_dump_tool_rows(concept_series))

        for provider_id in _dedupe_values(provider_ids):
            for concept_id in _dedupe_values(concept_ids):
                provider_series = await read_tools.list_provider_series_for_concept(
                    ListProviderSeriesForConceptArgs(
                        provider_id=provider_id,
                        concept_id=concept_id,
                    )
                )
                cohort_c.extend(_dump_tool_rows(provider_series))

        return {
            "cohort_a": _dedupe_rows(cohort_a),
            "cohort_b": _dedupe_rows(cohort_b),
            "cohort_c": _dedupe_rows(cohort_c),
        }

    return _cohort_lookup


def _first_present(item: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return None


def _dump_tool_rows(rows: list[Any]) -> list[dict[str, Any]]:
    dumped: list[dict[str, Any]] = []
    for row in rows:
        if hasattr(row, "model_dump"):
            dumped.append(row.model_dump(mode="json"))
        elif isinstance(row, dict):
            dumped.append(row)
        else:
            dumped.append(dict(row))
    return dumped


def _dedupe_values(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    deduped: list[Any] = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("id") or row.get("code") or row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _make_approval_llm(
    role_config: RoleConfig,
    *,
    client: openai.AsyncOpenAI,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Return an approval_llm that parses operator free-text into edit_instructions.

    For v1, passes the operator's pending_input through as edit_instructions.
    A future slice can replace this with a real LLM parse call.
    """
    async def _approval_llm(state: dict[str, Any]) -> dict[str, Any]:
        return {"edit_instructions": state.get("pending_input") or ""}

    return _approval_llm


def _make_test_reviewer(
    role_config: RoleConfig,
    *,
    client: openai.AsyncOpenAI,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Return a test_reviewer callable backed by OpenAI."""
    reviewer = make_openai_reviewer_callable(role_config, TestReviewOutput, client=client)

    async def _test_reviewer(review_input: dict[str, Any]) -> dict[str, Any]:
        messages = [{"role": "user", "content": json.dumps(review_input)}]
        return await reviewer(messages)

    return _test_reviewer


class _DbRunLogReader:
    """DB-backed run log reader matching FirstRunLogReaderProtocol."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_ingestion_run_log(self, run_log_id: str) -> dict[str, Any]:
        from sqlalchemy import select

        from macro_foundry.models import IngestionRunLog, IngestionRunLogMember

        run_log = await self._session.get(IngestionRunLog, run_log_id)
        if run_log is None:
            return {
                "run_log_id": run_log_id,
                "status": "unknown",
                "rows_fetched": 0,
                "rows_inserted": 0,
                "rows_skipped": 0,
                "diagnostics": {},
                "warnings": [],
            }

        member_log = await self._session.scalar(
            select(IngestionRunLogMember).where(
                IngestionRunLogMember.ingestion_run_log_id == run_log.id
            )
        )
        diagnostics = member_log.diagnostics if member_log is not None else {}
        return {
            "run_log_id": str(run_log.id),
            "status": run_log.status.value,
            "rows_fetched": run_log.rows_fetched,
            "rows_inserted": run_log.rows_inserted,
            "rows_skipped": run_log.rows_skipped,
            "diagnostics": diagnostics,
            "warnings": [],
        }


class _FilePackageStore:
    """File-backed package store for v1. Saves packages to ~/.macrodb/packages/."""

    async def save_onboarding_package(self, package: dict[str, Any]) -> dict[str, Any]:
        import uuid

        package_id = str(uuid.uuid4())
        save_dir = Path.home() / ".macrodb" / "packages"
        save_dir.mkdir(parents=True, exist_ok=True)
        path = save_dir / f"{package_id}.json"
        path.write_text(json.dumps(package, indent=2, default=str))
        return {"package_id": package_id, "path": str(path)}


def build_production_dependencies(
    role_configs: dict[AgentRole, RoleConfig],
    *,
    session: AsyncSession,
    client: openai.AsyncOpenAI | None = None,
) -> OnboardingGraphDependencies:
    """Build a complete OnboardingGraphDependencies from real backends.

    All LLM callables are backed by OpenAI structured outputs. Pickers are
    Questionary-backed. Write tools and run logs are DB-backed.
    The registry loads accepted skills from docs/skills/.
    """
    from macro_foundry.mcp.write_tools import MacrodbWriteTools

    effective_client = client or openai.AsyncOpenAI()

    research_llm = make_openai_llm_callable(
        role_configs[AgentRole.RESEARCHER], ResearchOutput, client=effective_client
    )
    draft_llm = make_openai_llm_callable(
        role_configs[AgentRole.PROPOSAL_DRAFTER], DraftOutput, client=effective_client
    )
    governance_llm = make_openai_reviewer_callable(
        role_configs[AgentRole.GOVERNANCE_REVIEWER], ReviewerOutput, client=effective_client
    )
    data_correctness_llm = make_openai_reviewer_callable(
        role_configs[AgentRole.DATA_CORRECTNESS_REVIEWER], ReviewerOutput, client=effective_client
    )
    extraction_mode_llm = make_openai_llm_callable(
        role_configs[AgentRole.APPROVAL_PARSER], ExtractionModeOutput, client=effective_client
    )
    approval_llm = _make_approval_llm(
        role_configs[AgentRole.APPROVAL_PARSER], client=effective_client
    )
    test_reviewer = _make_test_reviewer(
        role_configs[AgentRole.TEST_REVIEWER], client=effective_client
    )

    write_tools = MacrodbWriteTools(session)
    run_logs = _DbRunLogReader(session)
    package_store = _FilePackageStore()

    registry = SkillRegistry.from_directory(_SKILLS_DIR) if _SKILLS_DIR.exists() else SkillRegistry({})

    return OnboardingGraphDependencies(
        research_llm=research_llm,
        cohort_lookup=_make_cohort_lookup(session=session),
        extraction_mode_classifier=_make_extraction_mode_classifier(
            session=session,
            ambiguous_classifier=extraction_mode_llm,
        ),
        draft_llm=draft_llm,
        governance_llm=governance_llm,
        data_correctness_llm=data_correctness_llm,
        approval_llm=approval_llm,
        gate_1_picker=_questionary_picker,
        write_tools=write_tools,
        run_logs=run_logs,
        test_reviewer=test_reviewer,
        package_store=package_store,
        registry=registry,
    )


__all__ = ["build_production_dependencies"]
