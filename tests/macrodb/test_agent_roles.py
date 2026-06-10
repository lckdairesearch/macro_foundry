"""Role configuration coverage for the onboarding agent."""

from __future__ import annotations

import pytest

from macro_foundry.agent.roles import (
    AgentRole,
    LLMProvider,
    RoleOverride,
    apply_role_overrides,
    default_role_configs,
    resolve_model,
)


@pytest.mark.no_db
def test_default_role_configs_match_v1_reviewer_design() -> None:
    configs = default_role_configs()

    assert set(configs) == {
        AgentRole.RESEARCHER,
        AgentRole.PROPOSAL_DRAFTER,
        AgentRole.SCRIPT_DRAFTER,
        AgentRole.VALIDATOR,
        AgentRole.GOVERNANCE_REVIEWER,
        AgentRole.DATA_CORRECTNESS_REVIEWER,
        AgentRole.APPROVAL_PARSER,
        AgentRole.TEST_REVIEWER,
        AgentRole.DANGEROUS_CORRECTION_PLANNER,
    }
    assert "selector_reviewer" not in {role.value for role in configs}
    assert {config.provider for config in configs.values()} == {LLMProvider.OPENAI}
    assert resolve_model(configs[AgentRole.GOVERNANCE_REVIEWER], task_hint="selector_code_review") == (
        configs[AgentRole.GOVERNANCE_REVIEWER].models_by_task["selector_code_review"]
    )


@pytest.mark.no_db
def test_role_overrides_are_session_local() -> None:
    defaults = default_role_configs()

    overridden = apply_role_overrides(
        defaults,
        {
            AgentRole.RESEARCHER: RoleOverride(default_model="gpt-fast"),
            AgentRole.GOVERNANCE_REVIEWER: RoleOverride(deep_model="gpt-code-review"),
        },
    )

    assert resolve_model(overridden[AgentRole.RESEARCHER]) == "gpt-fast"
    assert (
        resolve_model(overridden[AgentRole.GOVERNANCE_REVIEWER], task_hint="selector_code_review")
        == "gpt-code-review"
    )
    assert resolve_model(defaults[AgentRole.RESEARCHER]) != "gpt-fast"
    assert (
        resolve_model(defaults[AgentRole.GOVERNANCE_REVIEWER], task_hint="selector_code_review")
        != "gpt-code-review"
    )
