"""Skill registry and prompt assembly for onboarding agent calls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class SkillStatus(str, Enum):
    """Runtime loading status declared by a Markdown skill."""

    STUB = "stub"
    DRAFT = "draft"
    ACCEPTED = "accepted"


class StatePredicate(BaseModel):
    """Serializable predicate evaluated against graph state."""

    model_config = ConfigDict(frozen=True)

    path: str
    equals: Any

    @classmethod
    def path_equals(cls, path: str, expected: Any) -> "StatePredicate":
        """Build a predicate requiring one dotted state path to equal a value."""

        return cls(path=path, equals=expected)

    def matches(self, state: dict[str, Any]) -> bool:
        """Evaluate this predicate against current graph state."""

        current: Any = state
        for part in self.path.split("."):
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
        return current == self.equals


class SkillTrigger(BaseModel):
    """One node-declared skill-loading trigger."""

    model_config = ConfigDict(frozen=True)

    trigger_id: str
    skill_id: str
    predicate: StatePredicate
    section_title: str | None = None


class LoadedSkillEvent(BaseModel):
    """Append-only record of a skill body loaded into an LLM prompt."""

    model_config = ConfigDict(frozen=True)

    skill_id: str
    trigger_id: str
    node: str
    section_title: str | None = None


class AssembledPrompt(BaseModel):
    """Prompt text plus the state events produced while assembling it."""

    model_config = ConfigDict(frozen=True)

    text: str
    loaded_skills: tuple[LoadedSkillEvent, ...]

    def state_update(self) -> dict[str, list[dict[str, Any]]]:
        """Return the append-only LangGraph state update for loaded skills."""

        return {
            "loaded_skills": [
                event.model_dump(mode="json") for event in self.loaded_skills
            ],
        }


@dataclass(frozen=True)
class SkillDocument:
    """Parsed Markdown skill."""

    skill_id: str
    status: SkillStatus
    body: str
    sections: dict[str, str]
    path: Path


class SkillRegistry:
    """Registry of Markdown skills by id."""

    def __init__(self, skills: dict[str, SkillDocument]) -> None:
        self._skills = skills

    @classmethod
    def from_directory(cls, directory: Path) -> "SkillRegistry":
        """Load all Markdown skills from a directory."""

        skills = {}
        for path in sorted(directory.glob("*.md")):
            if path.name == "README.md":
                continue
            document = _parse_skill(path)
            skills[document.skill_id] = document
        return cls(skills)

    def accepted_body(self, skill_id: str, section_title: str | None = None) -> str | None:
        """Return the loadable body for one accepted skill, or None."""

        skill = self._skills.get(skill_id)
        if skill is None or skill.status is not SkillStatus.ACCEPTED:
            return None
        if section_title is None:
            return skill.body
        return skill.sections.get(section_title)


def assemble_prompt(
    *,
    base_role_prompt: str,
    node: str,
    state: dict[str, Any],
    registry: SkillRegistry,
    skill_triggers: list[SkillTrigger],
) -> AssembledPrompt:
    """Assemble ``base_role_prompt + skill_bodies_in_predicate_order``."""

    bodies = [base_role_prompt]
    events: list[LoadedSkillEvent] = []
    for trigger in skill_triggers:
        if not trigger.predicate.matches(state):
            continue
        body = registry.accepted_body(trigger.skill_id, trigger.section_title)
        if body is None:
            continue
        bodies.append(body)
        events.append(
            LoadedSkillEvent(
                skill_id=trigger.skill_id,
                trigger_id=trigger.trigger_id,
                node=node,
                section_title=trigger.section_title,
            ),
        )
    return AssembledPrompt(text="\n\n".join(b for b in bodies if b), loaded_skills=tuple(events))


GOVERNANCE_SKILL_TRIGGERS = [
    SkillTrigger(
        trigger_id="governance-custom-python-selector-conventions",
        skill_id="skill-ingestion-selector-conventions",
        predicate=StatePredicate.path_equals("extraction_mode", "custom_python"),
    ),
]

METADATA_STANDARDISATION_SKILL_TRIGGERS = [
    SkillTrigger(
        trigger_id="metadata-standardisation-prose",
        skill_id="skill-metadata-standardisation",
        predicate=StatePredicate.path_equals("proposal.touches_prose", True),
    ),
    SkillTrigger(
        trigger_id="metadata-standardisation-seed-exemplars",
        skill_id="skill-metadata-standardisation",
        predicate=StatePredicate.path_equals("reference_metadata.cohort_A_empty", True),
        section_title="Seed exemplars",
    ),
]


def _parse_skill(path: Path) -> SkillDocument:
    text = path.read_text(encoding="utf-8")
    status, body = _split_frontmatter(text)
    body_section = _extract_markdown_section(body, "Body")
    if body_section is None:
        raise ValueError("skill Markdown must include a Body section")
    optional_sections = _optional_sections_for_skill(path.stem)
    sections = {
        section_title: section_body
        for section_title in optional_sections
        if (section_body := _extract_markdown_section(body_section, section_title)) is not None
    }
    return SkillDocument(
        skill_id=path.stem,
        status=status,
        body=_remove_markdown_sections(body_section, optional_sections).strip(),
        sections=sections,
        path=path,
    )


def _split_frontmatter(text: str) -> tuple[SkillStatus, str]:
    if not text.startswith("---\n"):
        raise ValueError("skill Markdown must start with frontmatter")
    _, frontmatter, body = text.split("---", maxsplit=2)
    status: SkillStatus | None = None
    for line in frontmatter.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() == "status":
            status = SkillStatus(value.strip())
            break
    if status is None:
        raise ValueError("skill frontmatter must declare status")
    return status, body


def _extract_markdown_section(body: str, section_title: str) -> str | None:
    lines = body.splitlines()
    start_index: int | None = None
    start_level: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        marker, _, title = stripped.partition(" ")
        if title.strip() != section_title:
            continue
        start_index = index + 1
        start_level = len(marker)
        break
    if start_index is None or start_level is None:
        return None
    end_index = len(lines)
    for index in range(start_index, len(lines)):
        stripped = lines[index].strip()
        if not stripped.startswith("#"):
            continue
        marker, _, _ = stripped.partition(" ")
        if len(marker) <= start_level:
            end_index = index
            break
    return "\n".join(lines[start_index:end_index]).strip()


def _remove_markdown_sections(body: str, section_titles: set[str]) -> str:
    if not section_titles:
        return body
    lines = body.splitlines()
    kept: list[str] = []
    skip_level: int | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            marker, _, title = stripped.partition(" ")
            if title.strip() in section_titles:
                skip_level = len(marker)
                continue
        if skip_level is None:
            kept.append(line)
    return "\n".join(kept)


def _optional_sections_for_skill(skill_id: str) -> set[str]:
    if skill_id == "skill-metadata-standardisation":
        return {"Seed exemplars"}
    return set()


__all__ = [
    "AssembledPrompt",
    "GOVERNANCE_SKILL_TRIGGERS",
    "LoadedSkillEvent",
    "METADATA_STANDARDISATION_SKILL_TRIGGERS",
    "SkillRegistry",
    "SkillStatus",
    "SkillTrigger",
    "StatePredicate",
    "assemble_prompt",
]
