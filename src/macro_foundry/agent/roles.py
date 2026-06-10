"""Typed LLM role configuration for the onboarding agent."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum


class LLMProvider(StrEnum):
    """Supported provider identifiers for role bindings."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


class AgentRole(StrEnum):
    """V1 onboarding agent roles."""

    RESEARCHER = "researcher"
    PROPOSAL_DRAFTER = "proposal_drafter"
    SCRIPT_DRAFTER = "script_drafter"
    VALIDATOR = "validator"
    GOVERNANCE_REVIEWER = "governance_reviewer"
    DATA_CORRECTNESS_REVIEWER = "data_correctness_reviewer"
    APPROVAL_PARSER = "approval_parser"
    TEST_REVIEWER = "test_reviewer"
    DANGEROUS_CORRECTION_PLANNER = "dangerous_correction_planner"


@dataclass(frozen=True)
class DecodeParams:
    """Decode parameters shared by model calls."""

    temperature: float = 0.2
    max_tokens: int = 4_000
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class RoleConfig:
    """LLM binding and prompt resources for one agent role."""

    role: AgentRole
    default_model: str
    provider: LLMProvider = LLMProvider.OPENAI
    models_by_task: dict[str, str] = field(default_factory=dict)
    decode: DecodeParams = field(default_factory=DecodeParams)
    tools: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoleOverride:
    """Session-local model override for one role."""

    default_model: str | None = None
    deep_model: str | None = None


OPENAI_DEFAULT_MODEL = "gpt-5.1"
OPENAI_DEEP_MODEL = "gpt-5.1-thinking"


def default_role_configs() -> dict[AgentRole, RoleConfig]:
    """Return the v1 OpenAI-bound role inventory."""

    return {
        AgentRole.RESEARCHER: RoleConfig(
            role=AgentRole.RESEARCHER,
            default_model=OPENAI_DEEP_MODEL,
            decode=DecodeParams(reasoning_effort="medium"),
            tools=("macrodb_read", "provider_fetch"),
            skills=("skill-hierarchy-enrichment", "skill-credential-gap"),
        ),
        AgentRole.PROPOSAL_DRAFTER: RoleConfig(
            role=AgentRole.PROPOSAL_DRAFTER,
            default_model=OPENAI_DEEP_MODEL,
            decode=DecodeParams(reasoning_effort="medium"),
            tools=("macrodb_write_proposals",),
            skills=("skill-metadata-standardisation", "skill-enum-gap-escalation"),
        ),
        AgentRole.SCRIPT_DRAFTER: RoleConfig(
            role=AgentRole.SCRIPT_DRAFTER,
            default_model=OPENAI_DEEP_MODEL,
            decode=DecodeParams(reasoning_effort="medium"),
            tools=("selector_schema", "selector_sandbox"),
            skills=("skill-ingestion-selector-conventions",),
        ),
        AgentRole.VALIDATOR: RoleConfig(
            role=AgentRole.VALIDATOR,
            default_model=OPENAI_DEFAULT_MODEL,
            tools=("selector_sandbox", "provider_fetch"),
        ),
        AgentRole.GOVERNANCE_REVIEWER: RoleConfig(
            role=AgentRole.GOVERNANCE_REVIEWER,
            default_model=OPENAI_DEEP_MODEL,
            models_by_task={"selector_code_review": OPENAI_DEEP_MODEL},
            decode=DecodeParams(reasoning_effort="high"),
            tools=("macrodb_read",),
            skills=(
                "skill-metadata-standardisation",
                "skill-enum-gap-escalation",
                "skill-credential-gap",
            ),
        ),
        AgentRole.DATA_CORRECTNESS_REVIEWER: RoleConfig(
            role=AgentRole.DATA_CORRECTNESS_REVIEWER,
            default_model=OPENAI_DEEP_MODEL,
            decode=DecodeParams(reasoning_effort="medium"),
            tools=("provider_fetch",),
        ),
        AgentRole.APPROVAL_PARSER: RoleConfig(
            role=AgentRole.APPROVAL_PARSER,
            default_model=OPENAI_DEFAULT_MODEL,
            decode=DecodeParams(temperature=0.0, max_tokens=1_000),
        ),
        AgentRole.TEST_REVIEWER: RoleConfig(
            role=AgentRole.TEST_REVIEWER,
            default_model=OPENAI_DEEP_MODEL,
            decode=DecodeParams(reasoning_effort="medium"),
            tools=("macrodb_read", "provider_fetch"),
        ),
        AgentRole.DANGEROUS_CORRECTION_PLANNER: RoleConfig(
            role=AgentRole.DANGEROUS_CORRECTION_PLANNER,
            default_model=OPENAI_DEEP_MODEL,
            decode=DecodeParams(reasoning_effort="high"),
            tools=("macrodb_read",),
            skills=("skill-dangerous-correction",),
        ),
    }


def resolve_model(config: RoleConfig, *, task_hint: str | None = None) -> str:
    """Resolve the model for a role call, honoring within-role task tiering."""

    if task_hint is not None and task_hint in config.models_by_task:
        return config.models_by_task[task_hint]
    return config.default_model


def with_default_model(config: RoleConfig, model: str) -> RoleConfig:
    """Return a session-local copy of a role config with a new default model."""

    return replace(config, default_model=model)


def apply_role_overrides(
    configs: dict[AgentRole, RoleConfig],
    overrides: dict[AgentRole, RoleOverride],
) -> dict[AgentRole, RoleConfig]:
    """Apply CLI model overrides to a copied role config map."""

    updated = dict(configs)
    for role, override in overrides.items():
        config = updated[role]
        if override.default_model is not None:
            config = replace(config, default_model=override.default_model)
        if override.deep_model is not None:
            task_models = dict(config.models_by_task)
            if task_models:
                for task_name in task_models:
                    task_models[task_name] = override.deep_model
            config = replace(config, models_by_task=task_models)
        updated[role] = config
    return updated


__all__ = [
    "AgentRole",
    "DecodeParams",
    "LLMProvider",
    "RoleConfig",
    "RoleOverride",
    "apply_role_overrides",
    "default_role_configs",
    "resolve_model",
    "with_default_model",
]
