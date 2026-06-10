"""End-to-end onboarding smoke tests for the FRED selector-runtime path."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from macro_foundry.agent.channel import ChannelEvent, ChannelPrompt, ChannelResponse
from macro_foundry.agent.credential_gap import CredentialProbeOutcome, make_credential_gap_wait_node
from macro_foundry.agent.enum_gap import make_enum_gap_wait_node
from macro_foundry.agent.graph import build_onboarding_smoke_graph
from macro_foundry.agent.roles import default_role_configs
from macro_foundry.agent.skills import SkillRegistry
from macro_foundry.enums import (
    Action,
    Frequency,
    IngestionRunStatus,
    Measure,
    OriginType,
    ProposalStatus,
    ProviderRole,
    SeasonalAdjustment,
    TargetType,
    TemporalStockFlow,
    UnitKind,
    UnitScale,
    ValidationStatus,
)
from macro_foundry.models import (
    ChangeProposal,
    ChangeProposalItem,
    Concept,
    Geography,
    IngestionFeedMember,
    IngestionRunLog,
    IngestionRunLogMember,
    Observation,
    Provider,
    ProviderCatalog,
    Series,
    SeriesFamily,
    SeriesFamilyMember,
    SeriesSource,
)
from macro_foundry.mcp.write_tools import MacrodbWriteTools

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


class _MemoryChannel:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def emit(self, event: ChannelEvent) -> None:
        self.events.append(event.text)

    async def prompt(self, prompt: ChannelPrompt) -> ChannelResponse:
        return ChannelResponse(text="approve")


class _RunLogReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_ingestion_run_log(self, run_log_id: str) -> dict[str, Any]:
        run_log = await self._session.get(IngestionRunLog, run_log_id)
        assert run_log is not None
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


class _PackageStore:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    async def save_onboarding_package(self, package: dict[str, Any]) -> dict[str, Any]:
        self.saved.append(package)
        return {"package_id": f"pkg-{len(self.saved)}"}


async def _approve_picker(options: list[str], *_args: Any) -> str:
    assert "approve" in options
    return "approve"


async def _approval_llm(_state: dict[str, Any]) -> dict[str, Any]:
    return {}


async def _reviewer_llm(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {
        "findings": [],
        "bounce_to_drafter": False,
        "prompt_tokens": 5,
        "completion_tokens": 5,
        "total_tokens": 10,
        "cost_estimate_usd": 0.0,
        "latency_ms": 1,
    }


async def _test_reviewer(_review_input: dict[str, Any]) -> dict[str, Any]:
    return {"summary": "First run passed against the recorded FRED payload."}


async def _config_only(_source_summary: str) -> str:
    return "config_only"


async def _empty_cohorts(_catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
    return {"cohort_a": [], "cohort_b": [], "cohort_c": []}


def _llm_usage(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "prompt_tokens": 10,
        "completion_tokens": 10,
        "total_tokens": 20,
        "cost_estimate_usd": 0.0,
        "latency_ms": 1,
    }


def _fred_selector_config() -> dict[str, Any]:
    return {
        "records_path": "observations",
        "period_anchor_field": "date",
        "value_field": "value",
        "frequency": Frequency.MONTHLY.value,
        "missing_value_tokens": [".", ""],
    }


def _draft_payload(series_code: str, *, concept_code: str | None = None) -> dict[str, Any]:
    concept = concept_code or f"CONCEPT_{series_code}"
    return {
        "concept": {
            "action": "new",
            "code": concept,
            "name": f"Concept {series_code}",
        },
        "family": {
            "action": "new",
            "code": f"FAM_{series_code}",
            "name": f"Family {series_code}",
            "concept_code": concept,
            "geography_code": "USA",
        },
        "series": {
            "action": "new",
            "code": series_code,
            "name": f"FRED {series_code}",
            "description": "US consumer price index from FRED.",
            "frequency": Frequency.MONTHLY.value,
            "measure": Measure.LEVEL.value,
            "unit_kind": UnitKind.INDEX.value,
            "temporal_stock_flow": TemporalStockFlow.INDEX.value,
            "unit_scale": UnitScale.ONE.value,
            "seasonal_adjustment": SeasonalAdjustment.NSA.value,
        },
        "source": {"provider_name": "USA FRED", "external_code": "CPIAUCNS"},
        "feed": {
            "selector_type": "json_path",
            "selector_config": _fred_selector_config(),
            "cron_schedule": "0 14 * * 5",
            "feed_method": "api",
            "fetch_url": "/series/observations",
        },
        "family_member": {"variant": "Headline NSA"},
    }


async def _run_smoke(
    session: AsyncSession,
    *,
    session_id: str,
    draft_outputs: list[dict[str, Any]],
    research_outputs: list[dict[str, Any]] | None = None,
    cohort_lookup: Any = _empty_cohorts,
    enum_gap_wait_node: Any | None = None,
    credential_gap_wait_node: Any | None = None,
) -> dict[str, Any]:
    research_queue = list(
        research_outputs
        or [
            {
                "source_summary": "FRED provides CPI observations through a JSON API.",
                "existing_catalog_hits": [],
                "ambiguity_flags": [],
                "credential_gap_proposals": [],
            }
        ]
    )
    draft_queue = list(draft_outputs)

    async def research_llm(_messages: list[dict[str, str]]) -> dict[str, Any]:
        return _llm_usage(research_queue.pop(0))

    async def draft_llm(_messages: list[dict[str, str]]) -> dict[str, Any]:
        return _llm_usage(draft_queue.pop(0))

    package_store = _PackageStore()
    graph = build_onboarding_smoke_graph(
        checkpointer=MemorySaver(),
        research_llm=research_llm,
        cohort_lookup=cohort_lookup,
        extraction_mode_classifier=_config_only,
        draft_llm=draft_llm,
        governance_llm=_reviewer_llm,
        data_correctness_llm=_reviewer_llm,
        approval_llm=_approval_llm,
        gate_1_picker=_approve_picker,
        channel=_MemoryChannel(),
        write_tools=MacrodbWriteTools(session),
        run_logs=_RunLogReader(session),
        test_reviewer=_test_reviewer,
        package_store=package_store,
        role_configs=default_role_configs(),
        registry=SkillRegistry({}),
        enum_gap_wait_node=enum_gap_wait_node,
        credential_gap_wait_node=credential_gap_wait_node,
    )

    payload = json.loads((_FIXTURES_DIR / "json_path_fred_observations.json").read_text())
    return await graph.ainvoke(
        {
            "pending_input": "Onboard FRED CPI sibling",
            "session_metadata": {"session_id": session_id},
            "first_run_payload": payload,
            "first_run_run_date": date(2026, 6, 10),
        },
        {"configurable": {"thread_id": session_id}},
    )


@pytest.mark.asyncio
async def test_happy_path_onboards_fred_cpi_and_emits_package(session: AsyncSession) -> None:
    session_id = "issue-52-happy"
    final_state = await _run_smoke(
        session,
        session_id=session_id,
        draft_outputs=[
            {
                "proposal": _draft_payload("ISSUE52_HAPPY_CPI"),
                "enum_gap_proposals": [],
                "harmonisation_items": [],
                "suggest_human_apply": [],
            }
        ],
    )

    assert final_state["onboarding_package"]["status"] == "test-approved"
    assert final_state["first_run"]["status"] == IngestionRunStatus.SUCCESS.value
    assert final_state["first_run"]["rows_inserted"] == 2

    proposal = await session.scalar(
        select(ChangeProposal).where(ChangeProposal.source_agent_session_id == session_id)
    )
    assert proposal is not None
    assert proposal.status is ProposalStatus.APPLIED

    member = await session.scalar(
        select(IngestionFeedMember).where(
            IngestionFeedMember.ingestion_feed_id == final_state["applied_catalog"]["feed_id"]
        )
    )
    assert member is not None
    assert member.selector_type == "json_path"
    assert member.selector_config == _fred_selector_config()

    observations = (
        await session.execute(
            select(Observation).where(Observation.series_id == final_state["applied_catalog"]["series_id"])
        )
    ).scalars().all()
    assert len(observations) == 2


@pytest.mark.asyncio
async def test_harmonisation_path_updates_existing_sibling_description(session: AsyncSession) -> None:
    sibling = await _create_existing_sibling(session, "ISSUE52_SIBLING_CPI")
    final_state = await _run_smoke(
        session,
        session_id="issue-52-harmonisation",
        draft_outputs=[
            {
                "proposal": _draft_payload("ISSUE52_HARMONISED_CPI"),
                "enum_gap_proposals": [],
                "harmonisation_items": [
                    {
                        "trigger": "factual_incompleteness",
                        "target_series_code": sibling.code,
                        "schema_field": "series.description",
                        "source_url": "https://fred.stlouisfed.org/series/CPIAUCNS",
                        "proposed_diff": "Add not-seasonally-adjusted qualifier.",
                        "proposed_value": "US CPI, not seasonally adjusted.",
                    }
                ],
                "suggest_human_apply": [],
            }
        ],
    )

    refreshed = await session.get(Series, sibling.id)
    assert refreshed is not None
    assert refreshed.description == "US CPI, not seasonally adjusted."
    assert final_state["onboarding_package"]["status"] == "test-approved"


@pytest.mark.asyncio
async def test_enum_gap_path_resolves_then_continues_to_package(session: AsyncSession) -> None:
    enum_gap = {
        "enum_path": "macro_foundry.enums.series.SeasonalAdjustment",
        "proposed_value": "NSA",
        "proposed_name": "NOT_SEASONALLY_ADJUSTED",
        "existing_values_considered": {
            "SA": "Seasonally adjusted is not correct.",
            "SAAR": "Annualized seasonally adjusted is not correct.",
            "unknown": "Provider documentation is explicit.",
        },
        "provider_evidence": {
            "url": "https://fred.stlouisfed.org/series/CPIAUCNS",
            "snippet": "Not Seasonally Adjusted",
        },
        "catalog_impact": "Seasonal-adjustment filters should classify this as NSA.",
        "rationale": "Provider publishes this CPI sibling as not seasonally adjusted.",
    }
    enum_wait = make_enum_gap_wait_node(db_enum_values=lambda _table, _column: ["NSA"])

    final_state = await _run_smoke(
        session,
        session_id="issue-52-enum-gap",
        enum_gap_wait_node=enum_wait,
        draft_outputs=[
            {
                "proposal": None,
                "enum_gap_proposals": [enum_gap],
                "harmonisation_items": [],
                "suggest_human_apply": [],
            },
            {
                "proposal": _draft_payload("ISSUE52_ENUM_CPI"),
                "enum_gap_proposals": [],
                "harmonisation_items": [],
                "suggest_human_apply": [],
            },
        ],
    )

    assert final_state["enum_gap_resolutions"][0]["outcome"] == "applied"
    assert final_state["onboarding_package"]["status"] == "test-approved"


@pytest.mark.asyncio
async def test_credential_gap_path_applies_provider_metadata_without_secret_leak(
    session: AsyncSession,
) -> None:
    provider = await session.scalar(select(Provider).where(Provider.name == "USA FRED"))
    assert provider is not None
    gap = {
        "provider_identity": {"kind": "existing", "existing_provider_id": str(provider.id)},
        "proposed_env_var_name": "ISSUE52_FRED_API_KEY",
        "proposed_auth_scheme": "query_param",
        "inferred_rate_limit": {"requests_per_minute": 120},
        "evidence_url": "https://fred.stlouisfed.org/docs/api/api_key.html",
        "evidence_snippet": "FRED API requests include an API key.",
        "rationale": "FRED probe requires an API key.",
    }
    secret = "issue-52-secret-value"

    async def probe(_name: str, credential: str) -> CredentialProbeOutcome:
        assert credential == secret
        return CredentialProbeOutcome.OK

    credential_wait = make_credential_gap_wait_node(
        write_tools=MacrodbWriteTools(session),
        environ={"ISSUE52_FRED_API_KEY": secret},
        probe=probe,
    )
    final_state = await _run_smoke(
        session,
        session_id="issue-52-credential",
        credential_gap_wait_node=credential_wait,
        research_outputs=[
            {
                "source_summary": "FRED requires API credentials.",
                "existing_catalog_hits": [],
                "ambiguity_flags": [],
                "credential_gap_proposals": [gap],
            },
            {
                "source_summary": "FRED provides CPI observations through a JSON API.",
                "existing_catalog_hits": [],
                "ambiguity_flags": [],
                "credential_gap_proposals": [],
            },
        ],
        draft_outputs=[
            {
                "proposal": _draft_payload("ISSUE52_CREDENTIAL_CPI"),
                "enum_gap_proposals": [],
                "harmonisation_items": [],
                "suggest_human_apply": [],
            }
        ],
    )

    refreshed = await session.get(Provider, provider.id)
    assert refreshed is not None
    assert refreshed.credentials_ref == "ISSUE52_FRED_API_KEY"
    assert refreshed.rate_limit_config == {"requests_per_minute": 120}
    assert secret not in json.dumps(final_state, sort_keys=True, default=str)


@pytest.mark.asyncio
async def test_suggest_human_apply_path_leaves_item_pending_then_admin_tool_marks_applied(
    session: AsyncSession,
) -> None:
    final_state = await _run_smoke(
        session,
        session_id="issue-52-suggest-human-apply",
        draft_outputs=[
            {
                "proposal": _draft_payload("ISSUE52_SHA_CPI"),
                "enum_gap_proposals": [],
                "harmonisation_items": [],
                "suggest_human_apply": [
                    {
                        "schema_field": "concept.name",
                        "proposed_value": "Consumer Price Index",
                        "rationale": "Use full title.",
                    }
                ],
            }
        ],
    )

    item = await session.scalar(
        select(ChangeProposalItem).where(
            ChangeProposalItem.action == Action.SUGGEST_HUMAN_APPLY,
            ChangeProposalItem.validation_status == ValidationStatus.PENDING_HUMAN_APPLY,
        )
    )
    assert item is not None
    assert item.target_type is TargetType.SERIES

    from macro_foundry.mcp.write_tools import MarkProposalOutcomeArgs

    result = await MacrodbWriteTools(session).mark_proposal_outcome(
        MarkProposalOutcomeArgs(
            proposal_id=item.id,
            status=ValidationStatus.APPLIED_BY_OPERATOR.value,
            applied_by="operator@test.example",
        )
    )
    assert result["validation_status"] == ValidationStatus.APPLIED_BY_OPERATOR.value
    assert final_state["onboarding_package"]["status"] == "test-approved"


async def _create_existing_sibling(session: AsyncSession, code: str) -> Series:
    geography = await session.scalar(select(Geography).where(Geography.code == "USA"))
    provider = await session.scalar(select(Provider).where(Provider.name == "USA FRED"))
    assert geography is not None
    assert provider is not None
    catalog = await session.scalar(
        select(ProviderCatalog).where(ProviderCatalog.provider_id == provider.id)
    )
    assert catalog is not None
    concept = Concept(code=f"CONCEPT_{code}", name=f"Concept {code}")
    session.add(concept)
    await session.flush()
    family = SeriesFamily(
        code=f"FAM_{code}",
        name=f"Family {code}",
        concept_id=concept.id,
        geography_id=geography.id,
    )
    session.add(family)
    await session.flush()
    series = Series(
        code=code,
        name=code,
        description="US CPI.",
        origin_type=OriginType.INGESTED,
        geography_id=geography.id,
        frequency=Frequency.MONTHLY,
        temporal_stock_flow=TemporalStockFlow.INDEX,
        unit_kind=UnitKind.INDEX,
        unit_scale=UnitScale.ONE,
        measure=Measure.LEVEL,
        annualized=False,
        seasonal_adjustment=SeasonalAdjustment.NSA,
        is_active=True,
    )
    session.add(series)
    await session.flush()
    session.add(
        SeriesFamilyMember(
            family_id=family.id,
            series_id=series.id,
            variant="Headline NSA",
            is_primary=True,
        )
    )
    await session.flush()
    session.add(
        SeriesSource(
            series_id=series.id,
            provider_catalog_id=catalog.id,
            external_code=code,
            priority=1,
            provider_role=ProviderRole.PRIMARY_SOURCE,
        )
    )
    await session.flush()
    return series
