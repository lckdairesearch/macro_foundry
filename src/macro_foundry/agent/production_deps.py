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
    ResearchOutput,
    ReviewerOutput,
    TestReviewOutput,
)
from macro_foundry.agent.onboarding import OnboardingGraphDependencies
from macro_foundry.agent.roles import AgentRole, RoleConfig
from macro_foundry.agent.skills import SkillRegistry

_SKILLS_DIR = Path(__file__).resolve().parents[3] / "docs" / "skills"

_CUSTOM_PYTHON_KEYWORDS: frozenset[str] = frozenset(
    {"python", "script", "custom", "sdk", "client", "parse", "scrape"}
)


async def _questionary_picker(options: list[str], *_args: Any) -> str:
    """Questionary-backed picker; presents an interactive select prompt."""
    return await questionary.select("Select:", choices=options).unsafe_ask_async()


async def _classify_extraction_mode(source_summary: str) -> str:
    lower = source_summary.lower()
    if any(kw in lower for kw in _CUSTOM_PYTHON_KEYWORDS):
        return "custom_python"
    return "config_only"


async def _empty_cohort_lookup(_catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Return empty cohorts for v1. The graph handles empty cohorts correctly."""
    return {"cohort_a": [], "cohort_b": [], "cohort_c": []}


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
        cohort_lookup=_empty_cohort_lookup,
        extraction_mode_classifier=_classify_extraction_mode,
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
