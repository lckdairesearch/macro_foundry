"""Typed LLM role configuration for the onboarding agent."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum


class LLMProvider(StrEnum):
    """Supported provider identifiers for role bindings."""

    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
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


@dataclass(frozen=True)
class ModelPreset:
    """Model + decode + provider bundle for one agent role.

    Separates the configurable model/provider/decode concern from the
    structural tools/skills concern in RoleConfig.  Swap a role's provider
    or model here without touching its tool/skill wiring.
    """

    model: str
    decode: DecodeParams = field(default_factory=DecodeParams)
    provider: LLMProvider = LLMProvider.OPENAI


_MEDIUM = ModelPreset("gpt-5.4", DecodeParams(reasoning_effort="medium"))
_HIGH = ModelPreset("gpt-5.4", DecodeParams(reasoning_effort="high"))
_CLASSIFIER = ModelPreset("gpt-5.4", DecodeParams(temperature=0.0, max_tokens=1_000))
_DEFAULT = ModelPreset("gpt-5.4")

DEFAULT_MODEL_CONFIGURATION: dict[AgentRole, ModelPreset] = {
    AgentRole.RESEARCHER:                   _MEDIUM,
    AgentRole.PROPOSAL_DRAFTER:             _MEDIUM,
    AgentRole.SCRIPT_DRAFTER:               _MEDIUM,
    AgentRole.VALIDATOR:                    _DEFAULT,
    AgentRole.GOVERNANCE_REVIEWER:          _HIGH,
    AgentRole.DATA_CORRECTNESS_REVIEWER:    _MEDIUM,
    AgentRole.APPROVAL_PARSER:              _CLASSIFIER,
    AgentRole.TEST_REVIEWER:                _MEDIUM,
    AgentRole.DANGEROUS_CORRECTION_PLANNER: _HIGH,
}


def _preset(role: AgentRole, **kwargs: object) -> RoleConfig:
    p = DEFAULT_MODEL_CONFIGURATION[role]
    return RoleConfig(
        role=role,
        default_model=p.model,
        decode=p.decode,
        provider=p.provider,
        **kwargs,  # type: ignore[arg-type]
    )


def default_role_configs() -> dict[AgentRole, RoleConfig]:
    """Return the v1 role inventory, pulling model/decode/provider from DEFAULT_MODEL_CONFIGURATION."""

    return {
        AgentRole.RESEARCHER: _preset(
            AgentRole.RESEARCHER,
            tools=("macrodb_read", "provider_fetch"),
            skills=("skill-hierarchy-enrichment", "skill-credential-gap"),
        ),
        AgentRole.PROPOSAL_DRAFTER: _preset(
            AgentRole.PROPOSAL_DRAFTER,
            tools=("macrodb_write_proposals",),
            skills=("skill-metadata-standardisation", "skill-enum-gap-escalation"),
        ),
        AgentRole.SCRIPT_DRAFTER: _preset(
            AgentRole.SCRIPT_DRAFTER,
            tools=("selector_schema", "selector_sandbox"),
            skills=("skill-ingestion-selector-conventions",),
        ),
        AgentRole.VALIDATOR: _preset(
            AgentRole.VALIDATOR,
            tools=("selector_sandbox", "provider_fetch"),
        ),
        AgentRole.GOVERNANCE_REVIEWER: _preset(
            AgentRole.GOVERNANCE_REVIEWER,
            models_by_task={"selector_code_review": DEFAULT_MODEL_CONFIGURATION[AgentRole.GOVERNANCE_REVIEWER].model},
            tools=("macrodb_read",),
            skills=(
                "skill-metadata-standardisation",
                "skill-enum-gap-escalation",
                "skill-credential-gap",
            ),
        ),
        AgentRole.DATA_CORRECTNESS_REVIEWER: _preset(
            AgentRole.DATA_CORRECTNESS_REVIEWER,
            tools=("provider_fetch",),
        ),
        AgentRole.APPROVAL_PARSER: _preset(AgentRole.APPROVAL_PARSER),
        AgentRole.TEST_REVIEWER: _preset(
            AgentRole.TEST_REVIEWER,
            tools=("macrodb_read", "provider_fetch"),
        ),
        AgentRole.DANGEROUS_CORRECTION_PLANNER: _preset(
            AgentRole.DANGEROUS_CORRECTION_PLANNER,
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
    "DEFAULT_MODEL_CONFIGURATION",
    "DecodeParams",
    "LLMProvider",
    "ModelPreset",
    "RoleConfig",
    "RoleOverride",
    "apply_role_overrides",
    "default_role_configs",
    "resolve_model",
    "with_default_model",
]
