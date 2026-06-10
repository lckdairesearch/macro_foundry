"""Credential-gap deterministic helper tests (issue 49)."""

from __future__ import annotations

import pytest

from macro_foundry.agent.credential_gap import (
    CredentialPrecheck,
    CredentialProbeOutcome,
    ProviderCredentialRecord,
    make_credential_gap_wait_node,
)
from macro_foundry.agent.escalation.picker import EscalationPickerResult, PickerOutcome


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_credential_precheck_uses_existing_provider_ref_before_probing() -> None:
    probes: list[tuple[str, str]] = []

    async def provider_lookup(provider_identity: dict[str, str]) -> ProviderCredentialRecord | None:
        assert provider_identity == {"kind": "existing", "existing_provider_id": "provider-1"}
        return ProviderCredentialRecord(credentials_ref="STORED_API_KEY")

    async def probe(env_var_name: str, credential: str) -> CredentialProbeOutcome:
        probes.append((env_var_name, credential))
        return CredentialProbeOutcome.OK

    precheck = CredentialPrecheck(
        provider_lookup=provider_lookup,
        environ={"STORED_API_KEY": "secret", "INFERRED_API_KEY": "wrong"},
        probe=probe,
    )

    result = await precheck.run(
        provider_identity={"kind": "existing", "existing_provider_id": "provider-1"},
        proposed_env_var_name="INFERRED_API_KEY",
    )

    assert result.passed is True
    assert result.env_var_name == "STORED_API_KEY"
    assert probes == [("STORED_API_KEY", "secret")]


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_credential_precheck_fails_without_env_value_and_skips_probe() -> None:
    async def provider_lookup(provider_identity: dict[str, str]) -> ProviderCredentialRecord | None:
        return None

    async def probe(env_var_name: str, credential: str) -> CredentialProbeOutcome:
        raise AssertionError("probe should not run when env var is unset")

    precheck = CredentialPrecheck(
        provider_lookup=provider_lookup,
        environ={},
        probe=probe,
    )

    result = await precheck.run(
        provider_identity={"kind": "new", "proposed_provider_name": "Example"},
        proposed_env_var_name="EXAMPLE_API_KEY",
    )

    assert result.passed is False
    assert result.reason == "missing_env"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_credential_precheck_caches_probe_by_provider_and_env_var() -> None:
    probe_count = 0

    async def provider_lookup(provider_identity: dict[str, str]) -> ProviderCredentialRecord | None:
        return None

    async def probe(env_var_name: str, credential: str) -> CredentialProbeOutcome:
        nonlocal probe_count
        probe_count += 1
        return CredentialProbeOutcome.AUTH_FAILED

    precheck = CredentialPrecheck(
        provider_lookup=provider_lookup,
        environ={"EXAMPLE_API_KEY": "secret"},
        probe=probe,
    )

    first = await precheck.run(
        provider_identity={"kind": "new", "proposed_provider_name": "Example"},
        proposed_env_var_name="EXAMPLE_API_KEY",
    )
    second = await precheck.run(
        provider_identity={"kind": "new", "proposed_provider_name": "Example"},
        proposed_env_var_name="EXAMPLE_API_KEY",
    )

    assert first.passed is False
    assert second.passed is False
    assert probe_count == 1


class _FakeWriteTools:
    def __init__(self) -> None:
        self.recorded: list[object] = []

    async def record_credential_gap_proposal(self, args: object) -> dict[str, str]:
        self.recorded.append(args)
        return {"proposal_id": "proposal-1", "item_id": "item-1"}


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_credential_gap_wait_offers_apply_later_or_abort_only() -> None:
    seen_options: list[str] = []
    write_tools = _FakeWriteTools()

    async def picker(**kwargs: object) -> EscalationPickerResult:
        options = kwargs["options"]
        seen_options.extend(option.outcome.value for option in options)  # type: ignore[attr-defined]
        return EscalationPickerResult(label="Apply later", outcome=PickerOutcome.APPLY_LATER)

    async def probe(env_var_name: str, credential: str) -> CredentialProbeOutcome:
        raise AssertionError("probe should not run when env var is unset")

    node = make_credential_gap_wait_node(
        write_tools=write_tools,
        environ={},
        probe=probe,
        picker=picker,
    )

    result = await node(
        {
            "session_metadata": {"session_id": "sess-credential-wait"},
            "credential_gap_proposals": [
                {
                    "provider_identity": {"kind": "new", "proposed_provider_name": "Example"},
                    "proposed_env_var_name": "EXAMPLE_API_KEY",
                    "proposed_auth_scheme": "bearer_header",
                    "inferred_rate_limit": None,
                    "evidence_url": "https://example.test/auth",
                    "evidence_snippet": "Use an API key.",
                    "rationale": "Docs require a key.",
                }
            ],
        }
    )

    assert seen_options == ["apply_later", "abort"]
    assert len(write_tools.recorded) == 1
    assert result["node_transitions"][0]["event"] == "paused"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_credential_gap_wait_records_resolution_when_resume_probe_succeeds() -> None:
    async def picker(**kwargs: object) -> EscalationPickerResult:
        raise AssertionError("picker should not render when probe succeeds")

    async def probe(env_var_name: str, credential: str) -> CredentialProbeOutcome:
        assert env_var_name == "EXAMPLE_API_KEY"
        assert credential == "secret"
        return CredentialProbeOutcome.OK

    node = make_credential_gap_wait_node(
        write_tools=_FakeWriteTools(),
        environ={"EXAMPLE_API_KEY": "secret"},
        probe=probe,
        picker=picker,
    )

    result = await node(
        {
            "credential_gap_proposals": [
                {
                    "provider_identity": {"kind": "new", "proposed_provider_name": "Example"},
                    "proposed_env_var_name": "EXAMPLE_API_KEY",
                    "proposed_auth_scheme": "bearer_header",
                    "inferred_rate_limit": {"requests_per_minute": 60},
                    "evidence_url": "https://example.test/auth",
                    "evidence_snippet": "Use an API key.",
                    "rationale": "Docs require a key.",
                }
            ],
        }
    )

    assert result["credential_gap_resolutions"][0]["outcome"] == "provisioned"
    assert result["credential_gap_resolutions"][0]["applied_env_var_name"] == "EXAMPLE_API_KEY"
    assert result["node_transitions"][0]["event"] == "resolved"
    assert "secret" not in repr(result)
