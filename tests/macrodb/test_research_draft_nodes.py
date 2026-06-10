"""Tests for research node, draft_proposal node, and DraftProposal model."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from macro_foundry.agent.onboarding import OnboardingTarget
from macro_foundry.agent.onboarding_state import (
    EnumGapProposal,
    OnboardingCheckpointState,
    SessionMetadata,
)
from macro_foundry.agent.proposal import (
    DraftConcept,
    DraftFamily,
    DraftFamilyMember,
    DraftHierarchyEdge,
    DraftIngestionFeed,
    DraftProposal,
    DraftSeries,
    DraftSeriesSource,
)


def _metadata(session_id: str = "s1") -> SessionMetadata:
    return SessionMetadata(
        session_id=session_id,
        target_environment=OnboardingTarget.DEV.value,
        created_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        created_by="macrodb-cli",
        cli_version="0.1.0",
    )


def _minimal_proposal() -> DraftProposal:
    return DraftProposal(
        concept=DraftConcept(action="new", code="CPI", name="Consumer Price Index"),
        family=DraftFamily(
            action="new",
            code="US_CPI",
            name="US CPI",
            concept_code="CPI",
            geography_code="USA",
        ),
        series=DraftSeries(
            action="new",
            code="US_CPI_SA_M",
            name="US CPI SA Monthly",
            frequency="monthly",
            measure="index_level",
            unit_kind="pure",
            temporal_stock_flow="index",
            unit_scale="one",
            seasonal_adjustment="NSA",
        ),
        source=DraftSeriesSource(provider_name="USA FRED", external_code="CPIAUCSL"),
        feed=DraftIngestionFeed(selector_type="json_path", cron_schedule="0 14 * * 5", feed_method="api"),
        family_member=DraftFamilyMember(variant="SA"),
    )


# ---------------------------------------------------------------------------
# DraftProposal model
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_draft_proposal_constructs_with_required_fields() -> None:
    proposal = _minimal_proposal()
    assert proposal.concept.code == "CPI"
    assert proposal.family.code == "US_CPI"
    assert proposal.series.frequency == "monthly"
    assert proposal.source.external_code == "CPIAUCSL"
    assert proposal.feed.selector_type == "json_path"
    assert proposal.family_member.variant == "SA"
    assert proposal.hierarchy_edges == ()


@pytest.mark.no_db
def test_draft_proposal_accepts_hierarchy_edges() -> None:
    proposal = DraftProposal(
        concept=DraftConcept(action="new", code="CPI", name="Consumer Price Index"),
        family=DraftFamily(
            action="new",
            code="US_CPI",
            name="US CPI",
            concept_code="CPI",
            geography_code="USA",
        ),
        series=DraftSeries(
            action="new",
            code="US_CPI_CORE_SA_M",
            name="US CPI Core SA Monthly",
            frequency="monthly",
            measure="index_level",
            unit_kind="pure",
            temporal_stock_flow="index",
            unit_scale="one",
            seasonal_adjustment="NSA",
        ),
        source=DraftSeriesSource(provider_name="USA FRED", external_code="CPILFESL"),
        feed=DraftIngestionFeed(selector_type="json_path", cron_schedule="0 14 * * 5", feed_method="api"),
        family_member=DraftFamilyMember(variant="Core SA"),
        hierarchy_edges=(
            DraftHierarchyEdge(
                parent_series_code="US_CPI_SA_M",
                child_series_code="US_CPI_CORE_SA_M",
                edge_kind="component",
            ),
        ),
    )
    assert len(proposal.hierarchy_edges) == 1
    assert proposal.hierarchy_edges[0].edge_kind == "component"


@pytest.mark.no_db
def test_draft_proposal_existing_action_does_not_require_description() -> None:
    proposal = DraftProposal(
        concept=DraftConcept(action="existing", code="CPI", name="Consumer Price Index"),
        family=DraftFamily(
            action="existing",
            code="US_CPI",
            name="US CPI",
            concept_code="CPI",
            geography_code="USA",
        ),
        series=DraftSeries(
            action="new",
            code="US_CPI_NSA_M",
            name="US CPI NSA Monthly",
            frequency="monthly",
            measure="index_level",
            unit_kind="pure",
            temporal_stock_flow="index",
            unit_scale="one",
            seasonal_adjustment="NSA",
        ),
        source=DraftSeriesSource(provider_name="USA FRED", external_code="CPIAUCNS"),
        feed=DraftIngestionFeed(selector_type="json_path", cron_schedule="0 14 * * 5", feed_method="api"),
        family_member=DraftFamilyMember(variant="NSA"),
    )
    assert proposal.concept.action == "existing"
    assert proposal.family.action == "existing"
    assert proposal.series.action == "new"


# ---------------------------------------------------------------------------
# State invariant: proposal blocked by enum_gap_proposals
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_state_invariant_allows_proposal_when_no_enum_gap_proposals() -> None:
    state = OnboardingCheckpointState(
        session_metadata=_metadata(),
        proposal=_minimal_proposal(),
        enum_gap_proposals=(),
    )
    assert state.proposal is not None


@pytest.mark.no_db
def test_state_invariant_blocks_proposal_when_enum_gap_proposals_non_empty() -> None:
    with pytest.raises(ValidationError, match="proposal cannot be set while enum_gap_proposals"):
        OnboardingCheckpointState(
            session_metadata=_metadata(),
            proposal=_minimal_proposal(),
            enum_gap_proposals=(
                EnumGapProposal(
                    column="frequency",
                    proposed_value="quarterly_avg",
                    rationale="Provider reports 3-month moving average, no existing value fits.",
                ),
            ),
        )


@pytest.mark.no_db
def test_state_allows_enum_gap_proposals_without_proposal() -> None:
    state = OnboardingCheckpointState(
        session_metadata=_metadata(),
        proposal=None,
        enum_gap_proposals=(
            EnumGapProposal(
                column="frequency",
                proposed_value="quarterly_avg",
                rationale="Provider reports 3-month moving average.",
            ),
        ),
    )
    assert len(state.enum_gap_proposals) == 1


# ---------------------------------------------------------------------------
# Research node
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_research_node_writes_source_summary_and_catalog_hits() -> None:
    from macro_foundry.agent.graph import make_research_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})  # empty registry

    async def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "source_summary": "FRED is the Federal Reserve Economic Data API.",
            "existing_catalog_hits": [{"code": "CPI", "kind": "concept"}],
            "ambiguity_flags": [],
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    role_config = default_role_configs()[AgentRole.RESEARCHER]
    node = make_research_node(fake_llm, role_config, registry)

    state = {
        "pending_input": "Onboard FRED CPI series",
        "raw_messages": [],
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    }

    result = await node(state)

    assert result["source_summary"] == "FRED is the Federal Reserve Economic Data API."
    assert result["existing_catalog_hits"] == [{"code": "CPI", "kind": "concept"}]
    assert result["ambiguity_flags"] == []


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_research_node_records_llm_call() -> None:
    from macro_foundry.agent.graph import make_research_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "source_summary": "BLS CPI data via FRED.",
            "existing_catalog_hits": [],
            "ambiguity_flags": [],
            "prompt_tokens": 80,
            "completion_tokens": 40,
            "total_tokens": 120,
            "cost_estimate_usd": 0.0008,
            "latency_ms": 175,
        }

    role_config = default_role_configs()[AgentRole.RESEARCHER]
    node = make_research_node(fake_llm, role_config, registry)

    result = await node({"pending_input": "Onboard FRED CPI", "llm_calls": [], "loaded_skills": [], "raw_messages": [], "node_transitions": []})

    assert len(result["llm_calls"]) == 1
    call = result["llm_calls"][0]
    assert call["role"] == "researcher"
    assert call["prompt_tokens"] == 80
    assert call["total_tokens"] == 120


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_research_node_surfaces_ambiguity_flags() -> None:
    from macro_foundry.agent.graph import make_research_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "source_summary": "Ambiguous provider.",
            "existing_catalog_hits": [],
            "ambiguity_flags": [
                "Series code US_CPI_SA_M may conflict with existing US_CPI_ALL_SA_M",
            ],
            "prompt_tokens": 90,
            "completion_tokens": 45,
            "total_tokens": 135,
            "cost_estimate_usd": 0.0009,
            "latency_ms": 190,
        }

    role_config = default_role_configs()[AgentRole.RESEARCHER]
    node = make_research_node(fake_llm, role_config, registry)

    result = await node({"pending_input": "Onboard ambiguous CPI", "llm_calls": [], "loaded_skills": [], "raw_messages": [], "node_transitions": []})

    assert result["ambiguity_flags"] == [
        "Series code US_CPI_SA_M may conflict with existing US_CPI_ALL_SA_M",
    ]


# ---------------------------------------------------------------------------
# Draft proposal node
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_proposal_node_writes_proposal() -> None:
    from macro_foundry.agent.graph import make_draft_proposal_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "proposal": {
                "concept": {"action": "new", "code": "CPI", "name": "Consumer Price Index"},
                "family": {
                    "action": "new",
                    "code": "US_CPI",
                    "name": "US CPI",
                    "concept_code": "CPI",
                    "geography_code": "USA",
                },
                "series": {
                    "action": "new",
                    "code": "US_CPI_SA_M",
                    "name": "US CPI SA Monthly",
                    "frequency": "monthly",
                    "measure": "index_level",
                    "unit_kind": "pure",
                    "temporal_stock_flow": "index",
                    "unit_scale": "one",
                    "seasonal_adjustment": "NSA",
                },
                "source": {"provider_name": "USA FRED", "external_code": "CPIAUCSL"},
                "feed": {"selector_type": "json_path", "cron_schedule": "0 14 * * 5", "feed_method": "api"},
                "family_member": {"variant": "SA"},
                "hierarchy_edges": [],
            },
            "enum_gap_proposals": [],
            "harmonisation_items": [],
            "suggest_human_apply": [],
            "prompt_tokens": 200,
            "completion_tokens": 150,
            "total_tokens": 350,
            "cost_estimate_usd": 0.003,
            "latency_ms": 400,
        }

    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_proposal_node(fake_llm, role_config, registry)

    state = {
        "source_summary": "FRED CPI data.",
        "existing_catalog_hits": [],
        "ambiguity_flags": [],
        "reference_metadata": {"cohort_a": [], "cohort_b": [], "cohort_c": [], "is_first_in_family": True},
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    }

    result = await node(state)

    assert result["proposal"] is not None
    proposal = DraftProposal.model_validate(result["proposal"])
    assert proposal.concept.code == "CPI"
    assert proposal.series.frequency == "monthly"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_proposal_node_records_llm_call() -> None:
    from macro_foundry.agent.graph import make_draft_proposal_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    registry = SkillRegistry({})

    async def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "proposal": {
                "concept": {"action": "new", "code": "CPI", "name": "CPI"},
                "family": {"action": "new", "code": "US_CPI", "name": "US CPI", "concept_code": "CPI", "geography_code": "USA"},
                "series": {"action": "new", "code": "US_CPI_SA_M", "name": "US CPI SA", "frequency": "monthly", "measure": "index_level", "unit_kind": "pure"},
                "source": {"provider_code": "FRED", "external_code": "CPIAUCSL"},
                "feed": {"selector_type": "json_path", "cron_schedule": "0 14 * * 5"},
                "family_member": {"variant": "SA"},
            },
            "enum_gap_proposals": [],
            "harmonisation_items": [],
            "suggest_human_apply": [],
            "prompt_tokens": 200,
            "completion_tokens": 100,
            "total_tokens": 300,
            "cost_estimate_usd": 0.002,
            "latency_ms": 350,
        }

    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_proposal_node(fake_llm, role_config, registry)

    result = await node({
        "source_summary": "FRED CPI.",
        "existing_catalog_hits": [],
        "ambiguity_flags": [],
        "reference_metadata": {"cohort_a": [], "cohort_b": [], "cohort_c": [], "is_first_in_family": True},
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert len(result["llm_calls"]) == 1
    call = result["llm_calls"][0]
    assert call["role"] == "proposal_drafter"
    assert call["total_tokens"] == 300


# ---------------------------------------------------------------------------
# Integration: research → draft_proposal happy path
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_research_then_draft_integration() -> None:
    """Full graph: research → gather + classify (parallel) → draft_proposal."""
    from macro_foundry.agent.graph import build_reference_metadata_graph
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry
    from typing import Any
    from langgraph.checkpoint.memory import MemorySaver

    registry = SkillRegistry({})
    role_configs = default_role_configs()

    research_calls: list[list[dict]] = []
    draft_calls: list[list[dict]] = []

    async def fake_research_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        research_calls.append(messages)
        return {
            "source_summary": "FRED provides US CPI data via JSON API.",
            "existing_catalog_hits": [],
            "ambiguity_flags": [],
            "prompt_tokens": 100,
            "completion_tokens": 60,
            "total_tokens": 160,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    async def fake_cohort_lookup(catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        return {"cohort_a": [], "cohort_b": [], "cohort_c": []}

    async def fake_classify(source_summary: str) -> str:
        return "config_only"

    async def fake_draft_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        draft_calls.append(messages)
        return {
            "proposal": {
                "concept": {"action": "new", "code": "CPI", "name": "Consumer Price Index"},
                "family": {"action": "new", "code": "US_CPI", "name": "US CPI", "concept_code": "CPI", "geography_code": "USA"},
                "series": {
                    "action": "new",
                    "code": "US_CPI_SA_M",
                    "name": "US CPI SA Monthly",
                    "frequency": "monthly",
                    "measure": "index_level",
                    "unit_kind": "pure",
                    "temporal_stock_flow": "index",
                    "unit_scale": "one",
                    "seasonal_adjustment": "NSA",
                },
                "source": {"provider_name": "USA FRED", "external_code": "CPIAUCSL"},
                "feed": {"selector_type": "json_path", "cron_schedule": "0 14 * * 5", "feed_method": "api"},
                "family_member": {"variant": "SA"},
            },
            "enum_gap_proposals": [],
            "harmonisation_items": [],
            "suggest_human_apply": [],
            "prompt_tokens": 200,
            "completion_tokens": 150,
            "total_tokens": 350,
            "cost_estimate_usd": 0.003,
            "latency_ms": 400,
        }

    checkpointer = MemorySaver()
    graph = build_reference_metadata_graph(
        checkpointer=checkpointer,
        research_llm=fake_research_llm,
        cohort_lookup=fake_cohort_lookup,
        extraction_mode_classifier=fake_classify,
        draft_llm=fake_draft_llm,
        role_configs=role_configs,
        registry=registry,
    )
    config = {"configurable": {"thread_id": "test-session-1"}}

    final_state = await graph.ainvoke(
        {"pending_input": "Onboard FRED US CPI monthly series"},
        config,
    )

    assert final_state["source_summary"] == "FRED provides US CPI data via JSON API."
    assert final_state["existing_catalog_hits"] == []

    proposal = DraftProposal.model_validate(final_state["proposal"])
    assert proposal.concept.code == "CPI"
    assert proposal.family.code == "US_CPI"
    assert proposal.series.code == "US_CPI_SA_M"
    assert proposal.series.frequency == "monthly"
    assert proposal.source.external_code == "CPIAUCSL"

    # research + draft nodes record LLM calls
    assert len(final_state["llm_calls"]) == 2
    roles = [c["role"] for c in final_state["llm_calls"]]
    assert "researcher" in roles
    assert "proposal_drafter" in roles

    # Both fake LLMs were called
    assert len(research_calls) == 1
    assert len(draft_calls) == 1
