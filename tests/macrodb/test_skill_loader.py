"""Skill registry and prompt-loader coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from macro_foundry.agent.skills import (
    GOVERNANCE_SKILL_TRIGGERS,
    METADATA_STANDARDISATION_SKILL_TRIGGERS,
    SkillRegistry,
    SkillTrigger,
    StatePredicate,
    assemble_prompt,
)


def write_skill(directory: Path, skill_id: str, status: str, body: str) -> None:
    directory.joinpath(f"{skill_id}.md").write_text(
        f"---\nstatus: {status}\n---\n# {skill_id}\n\n## Body\n\n{body}\n",
        encoding="utf-8",
    )


@pytest.mark.no_db
def test_prompt_loader_filters_out_stub_and_draft_skills(tmp_path: Path) -> None:
    write_skill(tmp_path, "skill-accepted", "accepted", "accepted body")
    write_skill(tmp_path, "skill-draft", "draft", "draft body")
    write_skill(tmp_path, "skill-stub", "stub", "stub body")
    registry = SkillRegistry.from_directory(tmp_path)

    prompt = assemble_prompt(
        base_role_prompt="base prompt",
        node="governance_review",
        state={"load": True},
        registry=registry,
        skill_triggers=[
            SkillTrigger(
                trigger_id="accepted-trigger",
                skill_id="skill-accepted",
                predicate=StatePredicate.path_equals("load", True),
            ),
            SkillTrigger(
                trigger_id="draft-trigger",
                skill_id="skill-draft",
                predicate=StatePredicate.path_equals("load", True),
            ),
            SkillTrigger(
                trigger_id="stub-trigger",
                skill_id="skill-stub",
                predicate=StatePredicate.path_equals("load", True),
            ),
        ],
    )

    assert prompt.text == "base prompt\n\naccepted body"
    assert [event.skill_id for event in prompt.loaded_skills] == ["skill-accepted"]
    assert prompt.state_update() == {
        "loaded_skills": [
            {
                "skill_id": "skill-accepted",
                "trigger_id": "accepted-trigger",
                "node": "governance_review",
                "section_title": None,
            },
        ],
    }


@pytest.mark.no_db
def test_project_skill_docs_parse_and_current_nonaccepted_skills_do_not_load() -> None:
    registry = SkillRegistry.from_directory(Path("docs/skills"))

    prompt = assemble_prompt(
        base_role_prompt="governance base",
        node="governance_review",
        state={"extraction_mode": "custom_python"},
        registry=registry,
        skill_triggers=GOVERNANCE_SKILL_TRIGGERS,
    )

    assert prompt.text == "governance base"
    assert prompt.loaded_skills == ()


@pytest.mark.no_db
def test_prompt_loader_uses_predicate_order_and_records_load_events(tmp_path: Path) -> None:
    write_skill(tmp_path, "skill-first", "accepted", "first body")
    write_skill(tmp_path, "skill-second", "accepted", "second body")
    write_skill(tmp_path, "skill-not-matched", "accepted", "not matched body")
    registry = SkillRegistry.from_directory(tmp_path)

    prompt = assemble_prompt(
        base_role_prompt="base prompt",
        node="draft_proposal",
        state={
            "proposal": {"touches_prose": True},
            "extraction_mode": "config_only",
        },
        registry=registry,
        skill_triggers=[
            SkillTrigger(
                trigger_id="second-trigger",
                skill_id="skill-second",
                predicate=StatePredicate.path_equals("proposal.touches_prose", True),
            ),
            SkillTrigger(
                trigger_id="first-trigger",
                skill_id="skill-first",
                predicate=StatePredicate.path_equals("proposal.touches_prose", True),
            ),
            SkillTrigger(
                trigger_id="not-matched-trigger",
                skill_id="skill-not-matched",
                predicate=StatePredicate.path_equals("extraction_mode", "custom_python"),
            ),
        ],
    )

    assert prompt.text == "base prompt\n\nsecond body\n\nfirst body"
    assert [(event.node, event.trigger_id, event.skill_id) for event in prompt.loaded_skills] == [
        ("draft_proposal", "second-trigger", "skill-second"),
        ("draft_proposal", "first-trigger", "skill-first"),
    ]


@pytest.mark.no_db
def test_governance_loads_selector_conventions_for_custom_python(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        "skill-ingestion-selector-conventions",
        "accepted",
        "selector review conventions",
    )
    registry = SkillRegistry.from_directory(tmp_path)

    prompt = assemble_prompt(
        base_role_prompt="governance base",
        node="governance_review",
        state={"extraction_mode": "custom_python"},
        registry=registry,
        skill_triggers=GOVERNANCE_SKILL_TRIGGERS,
    )

    assert prompt.text == "governance base\n\nselector review conventions"
    assert [(event.trigger_id, event.skill_id, event.node) for event in prompt.loaded_skills] == [
        (
            "governance-custom-python-selector-conventions",
            "skill-ingestion-selector-conventions",
            "governance_review",
        ),
    ]


@pytest.mark.no_db
def test_metadata_standardisation_seed_exemplars_load_only_when_cohort_a_empty(
    tmp_path: Path,
) -> None:
    tmp_path.joinpath("skill-metadata-standardisation.md").write_text(
        """---
status: accepted
---
# skill-metadata-standardisation

## Body

General prose rules.

### Seed exemplars

Seed exemplar rules.

### Later section

Do not include this.
""",
        encoding="utf-8",
    )
    registry = SkillRegistry.from_directory(tmp_path)

    prompt = assemble_prompt(
        base_role_prompt="draft base",
        node="draft_proposal",
        state={
            "draft_proposal_touches_prose": True,
            "is_first_in_family": True,
        },
        registry=registry,
        skill_triggers=METADATA_STANDARDISATION_SKILL_TRIGGERS,
    )

    assert prompt.text == "draft base\n\nGeneral prose rules.\n\nSeed exemplar rules."
    assert [(event.trigger_id, event.section_title) for event in prompt.loaded_skills] == [
        ("metadata-standardisation-prose", None),
        ("metadata-standardisation-seed-exemplars", "Seed exemplars"),
    ]

    prompt_without_exemplars = assemble_prompt(
        base_role_prompt="draft base",
        node="draft_proposal",
        state={
            "draft_proposal_touches_prose": True,
            "is_first_in_family": False,
        },
        registry=registry,
        skill_triggers=METADATA_STANDARDISATION_SKILL_TRIGGERS,
    )

    assert prompt_without_exemplars.text == "draft base\n\nGeneral prose rules."
