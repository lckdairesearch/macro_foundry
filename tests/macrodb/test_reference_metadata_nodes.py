"""Tests for gather_reference_metadata, classify_extraction_mode, and extended draft_proposal."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError


class _NoopChannel:
    async def emit(self, event: Any) -> None:
        pass

    async def prompt(self, prompt: Any) -> Any:
        raise AssertionError("prompt should not be called")


class _NoopWriteTools:
    async def propose_create_series(self, args: Any) -> dict[str, Any]:
        return {
            "proposal_id": "aaaaaaaa-0000-0000-0000-000000000001",
            "item_id": "aaaaaaaa-0000-0000-0000-000000000002",
            "series_id": "aaaaaaaa-0000-0000-0000-000000000003",
            "family_id": "aaaaaaaa-0000-0000-0000-000000000004",
            "concept_id": "aaaaaaaa-0000-0000-0000-000000000005",
            "feed_id": "aaaaaaaa-0000-0000-0000-000000000006",
        }

    async def record_suggest_human_apply(self, args: Any) -> dict[str, Any]:
        return {"proposal_id": "proposal-id", "item_ids": []}

    async def apply_credential_gap_resolutions(self, args: Any) -> dict[str, Any]:
        return {"applied": True}

    async def trigger_feed_execution(self, args: Any) -> dict[str, Any]:
        return {
            "feed_id": "aaaaaaaa-0000-0000-0000-000000000006",
            "run_log_id": "aaaaaaaa-0000-0000-0000-000000000007",
            "status": "success",
        }


class _NoopRunLogs:
    async def get_ingestion_run_log(self, run_log_id: str) -> dict[str, Any]:
        return {
            "run_log_id": run_log_id,
            "status": "success",
            "rows_fetched": 1,
            "rows_inserted": 1,
            "rows_skipped": 0,
            "diagnostics": {},
            "warnings": [],
        }


class _NoopPackageStore:
    async def save_onboarding_package(self, package: dict[str, Any]) -> dict[str, Any]:
        return {"package_id": "package-id"}


async def _approve_picker(options: list[str], *_args: Any) -> str:
    assert "approve" in options
    return "approve"


async def _approval_llm(_state: dict[str, Any]) -> dict[str, Any]:
    return {}


async def _reviewer_llm(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {
        "findings": [],
        "bounce_to_drafter": False,
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "total_tokens": 2,
        "cost_estimate_usd": 0.0,
        "latency_ms": 1,
    }


async def _test_reviewer(_review_input: dict[str, Any]) -> dict[str, Any]:
    return {"summary": "ok"}


def _noop_canonical_graph_kwargs() -> dict[str, Any]:
    return {
        "governance_llm": _reviewer_llm,
        "data_correctness_llm": _reviewer_llm,
        "approval_llm": _approval_llm,
        "gate_1_picker": _approve_picker,
        "channel": _NoopChannel(),
        "write_tools": _NoopWriteTools(),
        "run_logs": _NoopRunLogs(),
        "test_reviewer": _test_reviewer,
        "package_store": _NoopPackageStore(),
    }


# ---------------------------------------------------------------------------
# Slice 1 — ReferenceMetadata model
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_reference_metadata_stores_three_cohorts() -> None:
    from macro_foundry.agent.proposal import ReferenceMetadata

    meta = ReferenceMetadata(
        cohort_a=[{"code": "US_CPI_SA_M", "name": "US CPI SA Monthly"}],
        cohort_b=[{"code": "UK_CPI_SA_M", "name": "UK CPI SA Monthly"}],
        cohort_c=[],
        is_first_in_family=False,
    )
    assert len(meta.cohort_a) == 1
    assert meta.cohort_a[0]["code"] == "US_CPI_SA_M"
    assert meta.cohort_b[0]["code"] == "UK_CPI_SA_M"
    assert meta.cohort_c == ()
    assert meta.is_first_in_family is False


@pytest.mark.no_db
def test_reference_metadata_all_cohorts_empty_is_first_in_family() -> None:
    from macro_foundry.agent.proposal import ReferenceMetadata

    meta = ReferenceMetadata(
        cohort_a=[],
        cohort_b=[],
        cohort_c=[],
        is_first_in_family=True,
    )
    assert meta.cohort_a == ()
    assert meta.is_first_in_family is True


@pytest.mark.no_db
def test_reference_metadata_is_frozen() -> None:
    from macro_foundry.agent.proposal import ReferenceMetadata

    meta = ReferenceMetadata(cohort_a=[], cohort_b=[], cohort_c=[], is_first_in_family=True)
    with pytest.raises((AttributeError, TypeError, ValidationError)):
        meta.is_first_in_family = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Slice 2 — HarmonisationItem: evidence structure and drop-on-missing
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_harmonisation_item_factual_incompleteness_requires_evidence() -> None:
    from macro_foundry.agent.proposal import HarmonisationItem

    item = HarmonisationItem(
        trigger="factual_incompleteness",
        target_series_code="US_CPI_SA_M",
        schema_field="series.description",
        source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
        proposed_diff="Add 'seasonally adjusted' qualifier to description.",
    )
    assert item.trigger == "factual_incompleteness"
    assert item.schema_field == "series.description"


@pytest.mark.no_db
def test_harmonisation_item_factual_missing_schema_field_invalid() -> None:
    from macro_foundry.agent.proposal import HarmonisationItem

    with pytest.raises(ValidationError, match="schema_field"):
        HarmonisationItem(
            trigger="factual_incompleteness",
            target_series_code="US_CPI_SA_M",
            source_url="https://example.com",
            proposed_diff="Some diff.",
            # missing schema_field
        )


@pytest.mark.no_db
def test_harmonisation_item_factual_missing_source_url_invalid() -> None:
    from macro_foundry.agent.proposal import HarmonisationItem

    with pytest.raises(ValidationError, match="source_url"):
        HarmonisationItem(
            trigger="factual_error",
            target_series_code="US_CPI_SA_M",
            schema_field="series.description",
            proposed_diff="Some diff.",
            # missing source_url
        )


@pytest.mark.no_db
def test_harmonisation_item_outlier_requires_cohort_evidence() -> None:
    from macro_foundry.agent.proposal import HarmonisationItem

    item = HarmonisationItem(
        trigger="family_outlier",
        target_series_code="US_CPI_SA_M",
        cohort_members=["US_CPI_NSA_M", "US_CPI_CORE_SA_M"],
        shared_pattern="Description ends with 'not seasonally adjusted'",
        divergence="This series omits the seasonal adjustment qualifier.",
        proposed_diff="Append ', seasonally adjusted' to description.",
    )
    assert item.trigger == "family_outlier"
    assert item.cohort_members is not None
    assert len(item.cohort_members) == 2


@pytest.mark.no_db
def test_harmonisation_item_outlier_missing_cohort_members_invalid() -> None:
    from macro_foundry.agent.proposal import HarmonisationItem

    with pytest.raises(ValidationError, match="cohort_members"):
        HarmonisationItem(
            trigger="family_outlier",
            target_series_code="US_CPI_SA_M",
            shared_pattern="Some pattern",
            proposed_diff="Some diff.",
            # missing cohort_members
        )


@pytest.mark.no_db
def test_harmonisation_item_outlier_missing_shared_pattern_invalid() -> None:
    from macro_foundry.agent.proposal import HarmonisationItem

    with pytest.raises(ValidationError, match="shared_pattern"):
        HarmonisationItem(
            trigger="house_voice_outlier",
            target_series_code="US_CPI_SA_M",
            cohort_members=["UK_CPI_SA_M"],
            proposed_diff="Some diff.",
            # missing shared_pattern
        )


# ---------------------------------------------------------------------------
# Slice 3 — SuggestHumanApplyItem
# ---------------------------------------------------------------------------


@pytest.mark.no_db
def test_suggest_human_apply_item_constructs() -> None:
    from macro_foundry.agent.proposal import SuggestHumanApplyItem

    item = SuggestHumanApplyItem(
        schema_field="concept.name",
        proposed_value="Consumer Price Index",
        rationale="Provider uses full title; current name is an abbreviation.",
    )
    assert item.schema_field == "concept.name"
    assert item.proposed_value == "Consumer Price Index"


# ---------------------------------------------------------------------------
# Slice 4 — gather_reference_metadata node
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_gather_reference_metadata_writes_all_cohorts() -> None:
    from macro_foundry.agent.graph import make_gather_reference_metadata_node

    cohort_a = [{"code": "US_CPI_NSA_M", "name": "US CPI NSA Monthly"}]
    cohort_b = [{"code": "UK_CPI_SA_M", "name": "UK CPI SA Monthly"}]
    cohort_c = [{"code": "US_CPI_FRED_M", "name": "FRED US CPI Monthly"}]

    async def fake_cohort_lookup(catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        return {"cohort_a": cohort_a, "cohort_b": cohort_b, "cohort_c": cohort_c}

    node = make_gather_reference_metadata_node(fake_cohort_lookup)
    state = {
        "existing_catalog_hits": [{"code": "CPI", "kind": "concept"}],
        "node_transitions": [],
    }

    result = await node(state)

    from macro_foundry.agent.proposal import ReferenceMetadata
    meta = ReferenceMetadata.model_validate(result["reference_metadata"])
    assert len(meta.cohort_a) == 1
    assert meta.cohort_a[0]["code"] == "US_CPI_NSA_M"
    assert len(meta.cohort_b) == 1
    assert len(meta.cohort_c) == 1
    assert meta.is_first_in_family is False


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_gather_reference_metadata_sets_is_first_in_family_when_cohort_a_empty() -> None:
    from macro_foundry.agent.graph import make_gather_reference_metadata_node

    async def fake_cohort_lookup(catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        return {"cohort_a": [], "cohort_b": [], "cohort_c": []}

    node = make_gather_reference_metadata_node(fake_cohort_lookup)
    result = await node({"existing_catalog_hits": [], "node_transitions": []})

    from macro_foundry.agent.proposal import ReferenceMetadata
    meta = ReferenceMetadata.model_validate(result["reference_metadata"])
    assert meta.is_first_in_family is True


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_gather_reference_metadata_passes_catalog_hits_to_callable() -> None:
    from macro_foundry.agent.graph import make_gather_reference_metadata_node

    received_hits: list[list[dict]] = []

    async def fake_cohort_lookup(catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        received_hits.append(catalog_hits)
        return {"cohort_a": [], "cohort_b": [], "cohort_c": []}

    node = make_gather_reference_metadata_node(fake_cohort_lookup)
    hits = [{"code": "CPI", "kind": "concept", "id": "abc-123"}]
    await node({"existing_catalog_hits": hits, "node_transitions": []})

    assert received_hits == [hits]


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_gather_reference_metadata_records_node_transition() -> None:
    from macro_foundry.agent.graph import make_gather_reference_metadata_node

    async def fake_cohort_lookup(catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        return {"cohort_a": [], "cohort_b": [], "cohort_c": []}

    node = make_gather_reference_metadata_node(fake_cohort_lookup)
    result = await node({"existing_catalog_hits": [], "node_transitions": []})

    assert len(result["node_transitions"]) == 1
    assert result["node_transitions"][0]["node"] == "gather_reference_metadata"
    assert result["node_transitions"][0]["event"] == "completed"


# ---------------------------------------------------------------------------
# Slice 5 — classify_extraction_mode node
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_classify_extraction_mode_writes_config_only() -> None:
    from macro_foundry.agent.graph import make_classify_extraction_mode_node

    async def fake_classify(source_summary: str) -> str:
        return "config_only"

    node = make_classify_extraction_mode_node(fake_classify)
    result = await node({"source_summary": "FRED JSON API.", "node_transitions": []})

    assert result["extraction_mode"] == "config_only"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_classify_extraction_mode_writes_custom_python() -> None:
    from macro_foundry.agent.graph import make_classify_extraction_mode_node

    async def fake_classify(source_summary: str) -> str:
        return "custom_python"

    node = make_classify_extraction_mode_node(fake_classify)
    result = await node({"source_summary": "Bespoke SOAP endpoint.", "node_transitions": []})

    assert result["extraction_mode"] == "custom_python"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_classify_extraction_mode_passes_source_summary_to_callable() -> None:
    from macro_foundry.agent.graph import make_classify_extraction_mode_node

    received: list[str] = []

    async def fake_classify(source_summary: str) -> str:
        received.append(source_summary)
        return "config_only"

    node = make_classify_extraction_mode_node(fake_classify)
    await node({"source_summary": "FRED JSON API.", "node_transitions": []})

    assert received == ["FRED JSON API."]


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_classify_extraction_mode_records_node_transition() -> None:
    from macro_foundry.agent.graph import make_classify_extraction_mode_node

    async def fake_classify(source_summary: str) -> str:
        return "config_only"

    node = make_classify_extraction_mode_node(fake_classify)
    result = await node({"source_summary": "FRED.", "node_transitions": []})

    assert len(result["node_transitions"]) == 1
    assert result["node_transitions"][0]["node"] == "classify_extraction_mode"
    assert result["node_transitions"][0]["event"] == "completed"


# ---------------------------------------------------------------------------
# Slice 6 — draft_proposal Pydantic invariant: reference_metadata required
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_proposal_node_raises_if_reference_metadata_absent() -> None:
    from macro_foundry.agent.graph import make_draft_proposal_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    async def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "proposal": {},
            "enum_gap_proposals": [],
            "harmonisation_items": [],
            "suggest_human_apply": [],
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cost_estimate_usd": 0.0,
            "latency_ms": 10,
        }

    registry = SkillRegistry({})
    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_proposal_node(fake_llm, role_config, registry)

    with pytest.raises((ValueError, ValidationError)):
        await node({
            "source_summary": "FRED CPI.",
            "existing_catalog_hits": [],
            "reference_metadata": None,  # absent
            "llm_calls": [],
            "loaded_skills": [],
            "node_transitions": [],
        })


# ---------------------------------------------------------------------------
# Slice 7 — draft_proposal emits harmonisation_items (drop on missing evidence)
# ---------------------------------------------------------------------------


def _valid_reference_metadata_dict() -> dict[str, Any]:
    return {
        "cohort_a": [{"code": "US_CPI_NSA_M", "name": "US CPI NSA Monthly"}],
        "cohort_b": [],
        "cohort_c": [],
        "is_first_in_family": False,
    }


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_proposal_node_forwards_harmonisation_items_with_full_evidence() -> None:
    from macro_foundry.agent.graph import make_draft_proposal_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    valid_item = {
        "trigger": "factual_incompleteness",
        "target_series_code": "US_CPI_NSA_M",
        "schema_field": "series.description",
        "source_url": "https://fred.stlouisfed.org/series/CPIAUCNS",
        "proposed_diff": "Add 'not seasonally adjusted' qualifier.",
    }
    proposal_dict = {
        "concept": {"action": "new", "code": "CPI", "name": "Consumer Price Index"},
        "family": {"action": "new", "code": "US_CPI", "name": "US CPI", "concept_code": "CPI", "geography_code": "USA"},
        "series": {"action": "new", "code": "US_CPI_NSA_M", "name": "US CPI NSA Monthly", "frequency": "monthly", "measure": "index_level", "unit_kind": "pure", "temporal_stock_flow": "index", "unit_scale": "one", "seasonal_adjustment": "NSA"},
        "source": {"provider_name": "USA FRED", "external_code": "CPIAUCNS"},
        "feed": {"selector_type": "json_path", "cron_schedule": "0 14 * * 5"},
        "family_member": {"variant": "NSA"},
    }

    async def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "proposal": proposal_dict,
            "enum_gap_proposals": [],
            "harmonisation_items": [valid_item],
            "suggest_human_apply": [],
            "prompt_tokens": 200,
            "completion_tokens": 150,
            "total_tokens": 350,
            "cost_estimate_usd": 0.003,
            "latency_ms": 400,
        }

    registry = SkillRegistry({})
    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_proposal_node(fake_llm, role_config, registry)

    result = await node({
        "source_summary": "FRED CPI data.",
        "existing_catalog_hits": [],
        "reference_metadata": _valid_reference_metadata_dict(),
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert len(result["harmonisation_items"]) == 1
    assert result["harmonisation_items"][0]["trigger"] == "factual_incompleteness"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_proposal_node_drops_harmonisation_item_missing_schema_field() -> None:
    from macro_foundry.agent.graph import make_draft_proposal_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    invalid_item = {
        "trigger": "factual_incompleteness",
        "target_series_code": "US_CPI_NSA_M",
        # missing schema_field
        "source_url": "https://fred.stlouisfed.org/series/CPIAUCNS",
        "proposed_diff": "Some diff.",
    }
    proposal_dict = {
        "concept": {"action": "new", "code": "CPI", "name": "Consumer Price Index"},
        "family": {"action": "new", "code": "US_CPI", "name": "US CPI", "concept_code": "CPI", "geography_code": "USA"},
        "series": {"action": "new", "code": "US_CPI_NSA_M", "name": "US CPI NSA Monthly", "frequency": "monthly", "measure": "index_level", "unit_kind": "pure", "temporal_stock_flow": "index", "unit_scale": "one", "seasonal_adjustment": "NSA"},
        "source": {"provider_name": "USA FRED", "external_code": "CPIAUCNS"},
        "feed": {"selector_type": "json_path", "cron_schedule": "0 14 * * 5"},
        "family_member": {"variant": "NSA"},
    }

    async def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "proposal": proposal_dict,
            "enum_gap_proposals": [],
            "harmonisation_items": [invalid_item],
            "suggest_human_apply": [],
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    registry = SkillRegistry({})
    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_proposal_node(fake_llm, role_config, registry)

    result = await node({
        "source_summary": "FRED CPI data.",
        "existing_catalog_hits": [],
        "reference_metadata": _valid_reference_metadata_dict(),
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert result["harmonisation_items"] == []


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_proposal_node_drops_harmonisation_item_missing_cohort_members() -> None:
    from macro_foundry.agent.graph import make_draft_proposal_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    invalid_item = {
        "trigger": "family_outlier",
        "target_series_code": "US_CPI_SA_M",
        # missing cohort_members
        "shared_pattern": "Description ends with qualifier.",
        "proposed_diff": "Some diff.",
    }
    proposal_dict = {
        "concept": {"action": "new", "code": "CPI", "name": "Consumer Price Index"},
        "family": {"action": "new", "code": "US_CPI", "name": "US CPI", "concept_code": "CPI", "geography_code": "USA"},
        "series": {"action": "new", "code": "US_CPI_SA_M", "name": "US CPI SA Monthly", "frequency": "monthly", "measure": "index_level", "unit_kind": "pure", "temporal_stock_flow": "index", "unit_scale": "one", "seasonal_adjustment": "NSA"},
        "source": {"provider_name": "USA FRED", "external_code": "CPIAUCSL"},
        "feed": {"selector_type": "json_path", "cron_schedule": "0 14 * * 5"},
        "family_member": {"variant": "SA"},
    }

    async def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "proposal": proposal_dict,
            "enum_gap_proposals": [],
            "harmonisation_items": [invalid_item],
            "suggest_human_apply": [],
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    registry = SkillRegistry({})
    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_proposal_node(fake_llm, role_config, registry)

    result = await node({
        "source_summary": "FRED CPI data.",
        "existing_catalog_hits": [],
        "reference_metadata": _valid_reference_metadata_dict(),
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert result["harmonisation_items"] == []


# ---------------------------------------------------------------------------
# Slice 8 — draft_proposal emits suggest_human_apply items
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_proposal_node_forwards_suggest_human_apply() -> None:
    from macro_foundry.agent.graph import make_draft_proposal_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs
    from macro_foundry.agent.skills import SkillRegistry

    suggest_item = {
        "schema_field": "concept.name",
        "proposed_value": "Consumer Price Index",
        "rationale": "Full title per BLS publication.",
    }
    proposal_dict = {
        "concept": {"action": "new", "code": "CPI", "name": "Consumer Price Index"},
        "family": {"action": "new", "code": "US_CPI", "name": "US CPI", "concept_code": "CPI", "geography_code": "USA"},
        "series": {"action": "new", "code": "US_CPI_SA_M", "name": "US CPI SA Monthly", "frequency": "monthly", "measure": "index_level", "unit_kind": "pure", "temporal_stock_flow": "index", "unit_scale": "one", "seasonal_adjustment": "NSA"},
        "source": {"provider_name": "USA FRED", "external_code": "CPIAUCSL"},
        "feed": {"selector_type": "json_path", "cron_schedule": "0 14 * * 5"},
        "family_member": {"variant": "SA"},
    }

    async def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "proposal": proposal_dict,
            "enum_gap_proposals": [],
            "harmonisation_items": [],
            "suggest_human_apply": [suggest_item],
            "prompt_tokens": 200,
            "completion_tokens": 100,
            "total_tokens": 300,
            "cost_estimate_usd": 0.002,
            "latency_ms": 300,
        }

    registry = SkillRegistry({})
    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_proposal_node(fake_llm, role_config, registry)

    result = await node({
        "source_summary": "FRED CPI data.",
        "existing_catalog_hits": [],
        "reference_metadata": _valid_reference_metadata_dict(),
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert len(result["suggest_human_apply"]) == 1
    assert result["suggest_human_apply"][0]["schema_field"] == "concept.name"


# ---------------------------------------------------------------------------
# Slice 9 — Graph integration: new nodes in build_onboarding_graph
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_build_onboarding_graph_runs_all_nodes() -> None:
    """Full graph: research → gather + classify (parallel) → draft_proposal."""
    from macro_foundry.agent.graph import build_onboarding_graph
    from macro_foundry.agent.roles import default_role_configs
    from macro_foundry.agent.skills import SkillRegistry
    from macro_foundry.agent.proposal import DraftProposal
    from langgraph.checkpoint.memory import MemorySaver

    registry = SkillRegistry({})
    role_configs = default_role_configs()

    async def fake_research_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "source_summary": "FRED provides US CPI data via JSON API.",
            "existing_catalog_hits": [{"code": "CPI", "kind": "concept", "id": "abc-123"}],
            "ambiguity_flags": [],
            "prompt_tokens": 100,
            "completion_tokens": 60,
            "total_tokens": 160,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    async def fake_cohort_lookup(catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "cohort_a": [{"code": "US_CPI_NSA_M", "name": "US CPI NSA Monthly"}],
            "cohort_b": [],
            "cohort_c": [],
        }

    async def fake_classify(source_summary: str) -> str:
        return "config_only"

    async def fake_draft_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "proposal": {
                "concept": {"action": "existing", "code": "CPI", "name": "Consumer Price Index"},
                "family": {"action": "existing", "code": "US_CPI", "name": "US CPI", "concept_code": "CPI", "geography_code": "USA"},
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
    graph = build_onboarding_graph(
        checkpointer=checkpointer,
        research_llm=fake_research_llm,
        cohort_lookup=fake_cohort_lookup,
        extraction_mode_classifier=fake_classify,
        draft_llm=fake_draft_llm,
        role_configs=role_configs,
        registry=registry,
        **_noop_canonical_graph_kwargs(),
    )
    config = {"configurable": {"thread_id": "test-session-43"}}

    final_state = await graph.ainvoke(
        {"pending_input": "Onboard FRED US CPI SA monthly series"},
        config,
    )

    # Research results present
    assert final_state["source_summary"] == "FRED provides US CPI data via JSON API."

    # Reference metadata written by gather node
    from macro_foundry.agent.proposal import ReferenceMetadata
    meta = ReferenceMetadata.model_validate(final_state["reference_metadata"])
    assert len(meta.cohort_a) == 1
    assert meta.is_first_in_family is False

    # Extraction mode written by classify node
    assert final_state["extraction_mode"] == "config_only"

    # Proposal written by draft node
    proposal = DraftProposal.model_validate(final_state["proposal"])
    assert proposal.series.code == "US_CPI_SA_M"

    # All four nodes recorded transitions
    node_names = [t["node"] for t in final_state["node_transitions"]]
    assert "research" in node_names
    assert "gather_reference_metadata" in node_names
    assert "classify_extraction_mode" in node_names
    assert "draft_proposal" in node_names

    # LLM calls: research + draft + two reviewers in the canonical graph
    assert len(final_state["llm_calls"]) == 4


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_build_onboarding_graph_draft_anchors_on_cohort_a_and_emits_harmonisation() -> None:
    """
    Full graph: cohort A has a sibling that omits SA qualifier; draft emits a
    factual_incompleteness harmonisation item citing the sibling with evidence.
    """
    from macro_foundry.agent.graph import build_onboarding_graph
    from macro_foundry.agent.roles import default_role_configs
    from macro_foundry.agent.skills import SkillRegistry
    from macro_foundry.agent.proposal import ReferenceMetadata
    from langgraph.checkpoint.memory import MemorySaver

    registry = SkillRegistry({})
    role_configs = default_role_configs()

    async def fake_research_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "source_summary": "FRED provides US CPI data via JSON API.",
            "existing_catalog_hits": [{"code": "US_CPI", "kind": "family", "id": "fam-001"}],
            "ambiguity_flags": [],
            "prompt_tokens": 100,
            "completion_tokens": 60,
            "total_tokens": 160,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    async def fake_cohort_lookup(catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        # Cohort A has a sibling that omits SA qualifier in its description
        return {
            "cohort_a": [
                {
                    "code": "US_CPI_NSA_M",
                    "name": "US CPI NSA Monthly",
                    "description": "US consumer price index, monthly, all urban consumers.",
                }
            ],
            "cohort_b": [],
            "cohort_c": [],
        }

    async def fake_classify(source_summary: str) -> str:
        return "config_only"

    async def fake_draft_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        # Draft sees cohort A and notices US_CPI_NSA_M description lacks SA qualifier
        return {
            "proposal": {
                "concept": {"action": "existing", "code": "CPI", "name": "Consumer Price Index"},
                "family": {"action": "existing", "code": "US_CPI", "name": "US CPI", "concept_code": "CPI", "geography_code": "USA"},
                "series": {
                    "action": "new",
                    "code": "US_CPI_SA_M",
                    "name": "US CPI SA Monthly",
                    "description": "US consumer price index, monthly, all urban consumers, seasonally adjusted.",
                    "frequency": "monthly",
                    "measure": "index_level",
                    "unit_kind": "pure",
                    "temporal_stock_flow": "index",
                    "unit_scale": "one",
                    "seasonal_adjustment": "SA",
                },
                "source": {"provider_name": "USA FRED", "external_code": "CPIAUCSL"},
                "feed": {"selector_type": "json_path", "cron_schedule": "0 14 * * 5", "feed_method": "api"},
                "family_member": {"variant": "SA"},
            },
            "enum_gap_proposals": [],
            "harmonisation_items": [
                {
                    "trigger": "factual_incompleteness",
                    "target_series_code": "US_CPI_NSA_M",
                    "schema_field": "series.description",
                    "source_url": "https://fred.stlouisfed.org/series/CPIAUCNS",
                    "proposed_diff": "Append ', not seasonally adjusted' to description for completeness.",
                }
            ],
            "suggest_human_apply": [],
            "prompt_tokens": 200,
            "completion_tokens": 150,
            "total_tokens": 350,
            "cost_estimate_usd": 0.003,
            "latency_ms": 400,
        }

    checkpointer = MemorySaver()
    graph = build_onboarding_graph(
        checkpointer=checkpointer,
        research_llm=fake_research_llm,
        cohort_lookup=fake_cohort_lookup,
        extraction_mode_classifier=fake_classify,
        draft_llm=fake_draft_llm,
        role_configs=role_configs,
        registry=registry,
        **_noop_canonical_graph_kwargs(),
    )
    config = {"configurable": {"thread_id": "test-session-43-harmonisation"}}

    final_state = await graph.ainvoke(
        {"pending_input": "Onboard FRED US CPI SA monthly series"},
        config,
    )

    # Cohort A was populated and drove is_first_in_family = False
    meta = ReferenceMetadata.model_validate(final_state["reference_metadata"])
    assert len(meta.cohort_a) == 1
    assert meta.cohort_a[0]["code"] == "US_CPI_NSA_M"
    assert meta.is_first_in_family is False

    # Draft emitted exactly one harmonisation item for the sibling
    assert len(final_state["harmonisation_items"]) == 1
    item = final_state["harmonisation_items"][0]
    assert item["trigger"] == "factual_incompleteness"
    assert item["target_series_code"] == "US_CPI_NSA_M"
    assert item["schema_field"] == "series.description"
    assert "source_url" in item

    # No suggest_human_apply in this scenario
    assert final_state["suggest_human_apply"] == []


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_build_onboarding_graph_conditional_edge_reads_extraction_mode() -> None:
    """The conditional edge out of draft_proposal reads extraction_mode, not LLM output."""
    from macro_foundry.agent.graph import build_onboarding_graph, EDGE_NEXT_FROM_DRAFT
    from macro_foundry.agent.roles import default_role_configs
    from macro_foundry.agent.skills import SkillRegistry
    from langgraph.checkpoint.memory import MemorySaver

    registry = SkillRegistry({})
    role_configs = default_role_configs()
    checkpointer = MemorySaver()

    async def fake_research_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "source_summary": "Bespoke SOAP provider.",
            "existing_catalog_hits": [],
            "ambiguity_flags": [],
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cost_estimate_usd": 0.0,
            "latency_ms": 10,
        }

    async def fake_cohort_lookup(catalog_hits: list[dict[str, Any]]) -> dict[str, Any]:
        return {"cohort_a": [], "cohort_b": [], "cohort_c": []}

    async def fake_classify(source_summary: str) -> str:
        return "custom_python"

    async def fake_draft_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "proposal": {
                "concept": {"action": "new", "code": "GDP", "name": "GDP"},
                "family": {"action": "new", "code": "US_GDP", "name": "US GDP", "concept_code": "GDP", "geography_code": "USA"},
                "series": {"action": "new", "code": "US_GDP_Q", "name": "US GDP Quarterly", "frequency": "quarterly", "measure": "level", "unit_kind": "currency", "temporal_stock_flow": "flow", "unit_scale": "billion", "seasonal_adjustment": "SAAR", "currency_code": "USD"},
                "source": {"provider_name": "USA Bureau of Economic Analysis", "external_code": "GDP"},
                "feed": {"selector_type": "json_path", "cron_schedule": "0 14 * * 5", "feed_method": "api"},
                "family_member": {},
            },
            "enum_gap_proposals": [],
            "harmonisation_items": [],
            "suggest_human_apply": [],
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "cost_estimate_usd": 0.0,
            "latency_ms": 10,
        }

    graph = build_onboarding_graph(
        checkpointer=checkpointer,
        research_llm=fake_research_llm,
        cohort_lookup=fake_cohort_lookup,
        extraction_mode_classifier=fake_classify,
        draft_llm=fake_draft_llm,
        role_configs=role_configs,
        registry=registry,
        **_noop_canonical_graph_kwargs(),
    )
    config = {"configurable": {"thread_id": "test-session-43-b"}}

    final_state = await graph.ainvoke(
        {"pending_input": "Onboard bespoke GDP series"},
        config,
    )

    assert final_state["extraction_mode"] == "custom_python"
    # The conditional edge function is exported; call it directly to confirm routing
    edge_result = EDGE_NEXT_FROM_DRAFT(final_state)
    assert edge_result == "draft_script"


@pytest.mark.no_db
def test_draft_proposal_conditional_edge_prioritizes_enum_gap_wait() -> None:
    from macro_foundry.agent.graph import EDGE_NEXT_FROM_DRAFT

    edge_result = EDGE_NEXT_FROM_DRAFT(
        {
            "extraction_mode": "custom_python",
            "enum_gap_proposals": [
                {
                    "enum_path": "macro_foundry.enums.series.SeasonalAdjustment",
                    "proposed_value": "TCA",
                }
            ],
        }
    )

    assert edge_result == "enum_gap_wait"
