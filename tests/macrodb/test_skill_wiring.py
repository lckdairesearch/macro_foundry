"""End-to-end skill-wiring tests (issue 58).

Each test creates a real SkillDocument/SkillRegistry, calls the node factory,
and asserts that the returned ``loaded_skills`` state entries match what the
trigger predicates and accepted-skill filter should produce.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from macro_foundry.agent.skills import SkillDocument, SkillRegistry, SkillStatus


def _accepted_doc(skill_id: str, body: str, tmp_path: Path) -> SkillDocument:
    return SkillDocument(
        skill_id=skill_id,
        status=SkillStatus.ACCEPTED,
        body=body,
        sections={},
        path=tmp_path / f"{skill_id}.md",
    )


def _draft_doc(skill_id: str, tmp_path: Path) -> SkillDocument:
    return SkillDocument(
        skill_id=skill_id,
        status=SkillStatus.DRAFT,
        body="draft body",
        sections={},
        path=tmp_path / f"{skill_id}.md",
    )


def _fake_reviewer_llm() -> Any:
    async def _llm(messages: list[dict[str, str]], *, task_hint: str | None = None) -> dict[str, Any]:
        return {
            "findings": [],
            "bounce_to_drafter": False,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    return _llm


def _fake_draft_llm(proposal: dict[str, Any] | None = None) -> Any:
    async def _llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "proposal": proposal or {
                "concept": {"action": "new", "code": "CPI", "name": "CPI"},
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
            },
            "harmonisation_items": [],
            "enum_gap_proposals": [],
            "suggest_human_apply_items": [],
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    return _llm


# ---------------------------------------------------------------------------
# Slice 1 — governance_review node wires GOVERNANCE_SKILL_TRIGGERS
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_governance_review_populates_loaded_skills_for_custom_python(tmp_path: Path) -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    registry = SkillRegistry(
        {"skill-ingestion-selector-conventions": _accepted_doc("skill-ingestion-selector-conventions", "selector conventions body", tmp_path)}
    )
    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(_fake_reviewer_llm(), role_config, registry)

    result = await node({
        "proposal": {"concept": {"code": "CPI"}},
        "extraction_mode": "custom_python",
        "review_cycle": 0,
        "enum_gap_proposals": [],
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert result["loaded_skills"] == [
        {
            "skill_id": "skill-ingestion-selector-conventions",
            "trigger_id": "governance-custom-python-selector-conventions",
            "node": "governance_review",
            "section_title": None,
        }
    ]


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_governance_review_does_not_load_skill_for_config_only(tmp_path: Path) -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    registry = SkillRegistry(
        {"skill-ingestion-selector-conventions": _accepted_doc("skill-ingestion-selector-conventions", "selector conventions body", tmp_path)}
    )
    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(_fake_reviewer_llm(), role_config, registry)

    result = await node({
        "proposal": {},
        "extraction_mode": "config_only",
        "review_cycle": 0,
        "enum_gap_proposals": [],
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert result["loaded_skills"] == []


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_governance_review_does_not_load_draft_skill(tmp_path: Path) -> None:
    from macro_foundry.agent.graph import make_governance_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    registry = SkillRegistry(
        {"skill-ingestion-selector-conventions": _draft_doc("skill-ingestion-selector-conventions", tmp_path)}
    )
    role_config = default_role_configs()[AgentRole.GOVERNANCE_REVIEWER]
    node = make_governance_review_node(_fake_reviewer_llm(), role_config, registry)

    result = await node({
        "proposal": {},
        "extraction_mode": "custom_python",
        "review_cycle": 0,
        "enum_gap_proposals": [],
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert result["loaded_skills"] == []


# ---------------------------------------------------------------------------
# Slice 2 — draft_proposal node wires METADATA_STANDARDISATION_SKILL_TRIGGERS
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_proposal_populates_loaded_skills_when_touches_prose(tmp_path: Path) -> None:
    from macro_foundry.agent.graph import make_draft_proposal_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    registry = SkillRegistry(
        {"skill-metadata-standardisation": _accepted_doc("skill-metadata-standardisation", "metadata prose rules", tmp_path)}
    )
    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_proposal_node(_fake_draft_llm(), role_config, registry)

    result = await node({
        "pending_input": "Onboard CPI",
        "source_summary": "FRED CPI",
        "existing_catalog_hits": [],
        "coerce_hints": {},
        "coerce_rationales": {},
        "reference_metadata": {"cohort_A_empty": False},
        "proposal": {"touches_prose": True},
        "enum_gap_proposals": [],
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    skill_ids = [e["skill_id"] for e in result["loaded_skills"]]
    assert "skill-metadata-standardisation" in skill_ids
    assert any(
        e["trigger_id"] == "metadata-standardisation-prose"
        for e in result["loaded_skills"]
    )


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_proposal_loads_seed_exemplars_subsection_when_cohort_a_empty(tmp_path: Path) -> None:
    from macro_foundry.agent.graph import make_draft_proposal_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    doc = SkillDocument(
        skill_id="skill-metadata-standardisation",
        status=SkillStatus.ACCEPTED,
        body="General prose rules.",
        sections={"Seed exemplars": "Seed exemplar rules."},
        path=tmp_path / "skill-metadata-standardisation.md",
    )
    registry = SkillRegistry({"skill-metadata-standardisation": doc})
    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_proposal_node(_fake_draft_llm(), role_config, registry)

    result = await node({
        "pending_input": "Onboard CPI",
        "source_summary": "FRED CPI",
        "existing_catalog_hits": [],
        "coerce_hints": {},
        "coerce_rationales": {},
        "reference_metadata": {"cohort_A_empty": True},
        "proposal": {"touches_prose": True},
        "enum_gap_proposals": [],
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    trigger_ids = [e["trigger_id"] for e in result["loaded_skills"]]
    assert "metadata-standardisation-seed-exemplars" in trigger_ids
    seed_event = next(e for e in result["loaded_skills"] if e["trigger_id"] == "metadata-standardisation-seed-exemplars")
    assert seed_event["section_title"] == "Seed exemplars"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_draft_proposal_does_not_load_skill_when_prose_not_touched(tmp_path: Path) -> None:
    from macro_foundry.agent.graph import make_draft_proposal_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    registry = SkillRegistry(
        {"skill-metadata-standardisation": _accepted_doc("skill-metadata-standardisation", "metadata prose rules", tmp_path)}
    )
    role_config = default_role_configs()[AgentRole.PROPOSAL_DRAFTER]
    node = make_draft_proposal_node(_fake_draft_llm(), role_config, registry)

    result = await node({
        "pending_input": "Onboard CPI",
        "source_summary": "FRED CPI",
        "existing_catalog_hits": [],
        "coerce_hints": {},
        "coerce_rationales": {},
        "reference_metadata": {"cohort_A_empty": False},
        "proposal": {"touches_prose": False},
        "enum_gap_proposals": [],
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert result["loaded_skills"] == []


# ---------------------------------------------------------------------------
# Slice 3 — research and data_correctness nodes return empty loaded_skills
# ---------------------------------------------------------------------------


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_research_node_returns_empty_loaded_skills(tmp_path: Path) -> None:
    from macro_foundry.agent.graph import make_research_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    # Even with an accepted skill in the registry, research has no declared triggers
    registry = SkillRegistry(
        {"skill-credential-gap": _accepted_doc("skill-credential-gap", "credential gap body", tmp_path)}
    )
    role_config = default_role_configs()[AgentRole.RESEARCHER]

    async def fake_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "source_summary": "FRED CPI.",
            "existing_catalog_hits": [],
            "ambiguity_flags": [],
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cost_estimate_usd": 0.001,
            "latency_ms": 200,
        }

    node = make_research_node(fake_llm, role_config, registry)
    result = await node({
        "pending_input": "Onboard CPI",
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
        "raw_messages": [],
    })

    assert result["loaded_skills"] == []


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_data_correctness_review_returns_empty_loaded_skills(tmp_path: Path) -> None:
    from macro_foundry.agent.graph import make_data_correctness_review_node
    from macro_foundry.agent.roles import AgentRole, default_role_configs

    registry = SkillRegistry({})
    role_config = default_role_configs()[AgentRole.DATA_CORRECTNESS_REVIEWER]
    node = make_data_correctness_review_node(_fake_reviewer_llm(), role_config, registry)

    result = await node({
        "proposal": {},
        "review_cycle": 0,
        "llm_calls": [],
        "loaded_skills": [],
        "node_transitions": [],
    })

    assert result["loaded_skills"] == []
