"""Credential-gap pre-check helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any

from macro_foundry.agent.escalation.picker import (
    EscalationPickerOption,
    EscalationPickerResult,
    OperatorInstructionBlock,
    PickerOutcome,
    render_escalation_picker,
)
from macro_foundry.agent.onboarding_state import NodeTransition
from macro_foundry.agent.proposal import CredentialGapProposal, CredentialGapResolution


class CredentialProbeOutcome(str, Enum):
    """Credential probe result bucket."""

    OK = "ok"
    AUTH_FAILED = "auth_failed"
    TRANSIENT = "transient"


@dataclass(frozen=True)
class ProviderCredentialRecord:
    """Provider access metadata needed before probing."""

    credentials_ref: str | None = None


@dataclass(frozen=True)
class CredentialPrecheckResult:
    """Result of the three-layer credential pre-check."""

    passed: bool
    env_var_name: str
    reason: str
    probe_outcome: CredentialProbeOutcome | None = None


ProviderLookup = Callable[[dict[str, str]], Awaitable[ProviderCredentialRecord | None]]
CredentialProbe = Callable[[str, str], Awaitable[CredentialProbeOutcome]]
CredentialGapPicker = Callable[..., Awaitable[EscalationPickerResult]]


class CredentialPrecheck:
    """Run ADR 0016's cached three-layer credential pre-check."""

    def __init__(
        self,
        *,
        provider_lookup: ProviderLookup,
        environ: Mapping[str, str],
        probe: CredentialProbe,
    ) -> None:
        self._provider_lookup = provider_lookup
        self._environ = environ
        self._probe = probe
        self._cache: dict[tuple[str, str], CredentialPrecheckResult] = {}

    async def run(
        self,
        *,
        provider_identity: dict[str, str],
        proposed_env_var_name: str,
    ) -> CredentialPrecheckResult:
        provider_record = await self._provider_lookup(provider_identity)
        env_var_name = (
            provider_record.credentials_ref
            if provider_record and provider_record.credentials_ref
            else proposed_env_var_name
        )

        cache_key = (_provider_identity_key(provider_identity), env_var_name)
        if cache_key in self._cache:
            return self._cache[cache_key]

        credential = self._environ.get(env_var_name)
        if not credential:
            result = CredentialPrecheckResult(
                passed=False,
                env_var_name=env_var_name,
                reason="missing_env",
            )
            self._cache[cache_key] = result
            return result

        outcome = await self._probe(env_var_name, credential)
        if outcome == CredentialProbeOutcome.OK:
            result = CredentialPrecheckResult(
                passed=True,
                env_var_name=env_var_name,
                reason="probe_ok",
                probe_outcome=outcome,
            )
        elif outcome == CredentialProbeOutcome.AUTH_FAILED:
            result = CredentialPrecheckResult(
                passed=False,
                env_var_name=env_var_name,
                reason="auth_failed",
                probe_outcome=outcome,
            )
        else:
            result = CredentialPrecheckResult(
                passed=False,
                env_var_name=env_var_name,
                reason="transient",
                probe_outcome=outcome,
            )
        self._cache[cache_key] = result
        return result


def _provider_identity_key(provider_identity: dict[str, str]) -> str:
    return json.dumps(provider_identity, sort_keys=True, separators=(",", ":"))


def make_credential_gap_wait_node(
    *,
    write_tools: Any,
    environ: Mapping[str, str],
    probe: CredentialProbe,
    picker: CredentialGapPicker = render_escalation_picker,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return the credential_gap_wait node."""

    async def _credential_gap_wait_node(state: dict[str, Any]) -> dict[str, Any]:
        from macro_foundry.mcp.write_tools import RecordCredentialGapProposalArgs

        raw_proposals = state.get("credential_gap_proposals") or []
        proposals = [CredentialGapProposal.model_validate(raw) for raw in raw_proposals]
        if not proposals:
            return {}

        resolutions: list[dict[str, Any]] = []
        session_id = (state.get("session_metadata") or {}).get("session_id", "")
        now = datetime.now(timezone.utc)

        for proposal in proposals:
            credential = environ.get(proposal.proposed_env_var_name)
            if credential:
                outcome = await probe(proposal.proposed_env_var_name, credential)
                if outcome == CredentialProbeOutcome.OK:
                    resolution = CredentialGapResolution(
                        outcome="provisioned",
                        provider_identity=proposal.provider_identity,
                        applied_env_var_name=proposal.proposed_env_var_name,
                        applied_auth_scheme=proposal.proposed_auth_scheme,
                        applied_rate_limit_config=proposal.inferred_rate_limit,
                        resolved_at=now,
                    )
                    resolutions.append(resolution.model_dump(mode="json"))
                    continue

            result = await picker(
                prompt="Credential required",
                options=(
                    EscalationPickerOption(
                        label="Apply later",
                        outcome=PickerOutcome.APPLY_LATER,
                    ),
                    EscalationPickerOption(
                        label="Abort",
                        outcome=PickerOutcome.ABORT,
                    ),
                ),
                instruction_blocks=(
                    OperatorInstructionBlock(
                        title=f"Credential required for {proposal.provider_identity.kind} provider",
                        body=(
                            f"Set {proposal.proposed_env_var_name} outside macrodb, then resume. "
                            f"Auth scheme: {proposal.proposed_auth_scheme}. "
                            f"Evidence: {proposal.evidence_url}"
                        ),
                    ),
                ),
            )
            if result.outcome == PickerOutcome.APPLY_LATER:
                await write_tools.record_credential_gap_proposal(
                    RecordCredentialGapProposalArgs(
                        gap=proposal.model_dump(mode="json"),
                        session_id=session_id,
                    )
                )
                return {
                    "node_transitions": [
                        NodeTransition(
                            node="credential_gap_wait",
                            event="paused",
                            created_at=now,
                        ).model_dump(mode="json")
                    ]
                }
            return {
                "credential_gap_resolutions": [
                    CredentialGapResolution(
                        outcome="aborted",
                        operator_rationale="credential_unavailable",
                        resolved_at=now,
                    ).model_dump(mode="json")
                ],
                "node_transitions": [
                    NodeTransition(
                        node="credential_gap_wait",
                        event="aborted",
                        created_at=now,
                    ).model_dump(mode="json")
                ],
            }

        return {
            "credential_gap_resolutions": resolutions,
            "node_transitions": [
                NodeTransition(
                    node="credential_gap_wait",
                    event="resolved",
                    created_at=now,
                ).model_dump(mode="json")
            ],
        }

    return _credential_gap_wait_node


__all__ = [
    "CredentialPrecheck",
    "CredentialPrecheckResult",
    "CredentialProbeOutcome",
    "make_credential_gap_wait_node",
    "ProviderCredentialRecord",
]
