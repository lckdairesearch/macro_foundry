"""Shared escalation helper coverage."""

from __future__ import annotations

import pytest

from macro_foundry.agent.escalation.audit import emit_gap_audit_row
from macro_foundry.agent.escalation.picker import (
    EscalationPickerOption,
    OperatorInstructionBlock,
    PickerOutcome,
    render_escalation_picker,
)
from macro_foundry.enums import (
    Action,
    ItemType,
    ProposalStatus,
    ProposalType,
    RequestedBy,
    RiskLevel,
    TargetType,
    ValidationStatus,
)
from macro_foundry.agent.escalation.lifecycle import (
    GapVerification,
    pause_and_exit,
    resume_walk,
)


class FakePrompt:
    def __init__(self, selected: str) -> None:
        self.selected = selected

    async def unsafe_ask_async(self) -> str:
        return self.selected


class FakeQuestionary:
    def __init__(self, selected: str) -> None:
        self.selected = selected
        self.calls: list[dict[str, object]] = []

    def select(self, message: str, *, choices: list[str]) -> FakePrompt:
        self.calls.append({"message": message, "choices": choices})
        return FakePrompt(self.selected)


class FakeConsole:
    def __init__(self) -> None:
        self.rendered: list[str] = []

    def print(self, text: str) -> None:
        self.rendered.append(text)


class FakeChangeProposalStore:
    def __init__(self) -> None:
        self.proposals: list[dict[str, object]] = []
        self.items: list[dict[str, object]] = []

    async def create_change_proposal(self, payload: dict[str, object]) -> str:
        proposal_id = f"proposal-{len(self.proposals) + 1}"
        self.proposals.append({"id": proposal_id, **payload})
        return proposal_id

    async def create_change_proposal_item(self, payload: dict[str, object]) -> str:
        item_id = f"item-{len(self.items) + 1}"
        self.items.append({"id": item_id, **payload})
        return item_id


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_picker_renders_instruction_blocks_and_returns_structured_outcome() -> None:
    questionary = FakeQuestionary("Abort")
    console = FakeConsole()

    result = await render_escalation_picker(
        prompt="Credential required",
        options=(
            EscalationPickerOption(label="Apply later (pause)", outcome=PickerOutcome.APPLY_LATER),
            EscalationPickerOption(label="Abort", outcome=PickerOutcome.ABORT),
        ),
        instruction_blocks=(
            OperatorInstructionBlock.from_template(
                title="Set credential",
                template="export {env_var}=...",
                values={"env_var": "FRED_API_KEY"},
            ),
        ),
        questionary_module=questionary,
        console=console,
    )

    assert console.rendered == ["Set credential\nexport FRED_API_KEY=..."]
    assert questionary.calls == [
        {
            "message": "Credential required",
            "choices": ["Apply later (pause)", "Abort"],
        },
    ]
    assert result.outcome is PickerOutcome.ABORT
    assert result.label == "Abort"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_picker_supports_three_option_enum_gap_dispatch() -> None:
    questionary = FakeQuestionary("Decline and coerce")

    result = await render_escalation_picker(
        prompt="Enum value missing",
        options=(
            EscalationPickerOption(label="Apply later (pause)", outcome=PickerOutcome.APPLY_LATER),
            EscalationPickerOption(label="Decline and coerce", outcome=PickerOutcome.DECLINE_AND_COERCE),
            EscalationPickerOption(label="Abort", outcome=PickerOutcome.ABORT),
        ),
        questionary_module=questionary,
        console=FakeConsole(),
    )

    assert questionary.calls == [
        {
            "message": "Enum value missing",
            "choices": ["Apply later (pause)", "Decline and coerce", "Abort"],
        },
    ]
    assert result.outcome is PickerOutcome.DECLINE_AND_COERCE


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_lifecycle_pause_preserves_position_and_resume_walk_verifies_unresolved_gaps() -> None:
    state = {
        "session_id": "onboard-abc",
        "checkpoint_position": "enum_gap_wait",
        "enum_gap_proposals": [{"gap_id": "gap-1"}, {"gap_id": "gap-2"}],
        "enum_gap_resolutions": [{"gap_id": "gap-1", "outcome": "applied"}],
    }
    verified_gap_ids: list[str] = []

    async def verifier(gap: dict[str, str]) -> GapVerification:
        verified_gap_ids.append(gap["gap_id"])
        return GapVerification(
            gap_id=gap["gap_id"],
            resolved=True,
            resolution={"gap_id": gap["gap_id"], "outcome": "applied"},
        )

    pause = pause_and_exit(state)

    assert pause.session_id == "onboard-abc"
    assert pause.checkpoint_position == "enum_gap_wait"
    assert pause.exit_code == 0
    assert state["checkpoint_position"] == "enum_gap_wait"

    resumed = await resume_walk(
        state,
        verifier,
        gap_field="enum_gap_proposals",
        resolution_field="enum_gap_resolutions",
    )

    assert verified_gap_ids == ["gap-2"]
    assert resumed.all_resolved is True
    assert resumed.state["enum_gap_resolutions"] == [
        {"gap_id": "gap-1", "outcome": "applied"},
        {"gap_id": "gap-2", "outcome": "applied"},
    ]


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_audit_emits_one_change_proposal_row_per_gap_with_caller_supplied_values() -> None:
    store = FakeChangeProposalStore()

    first = await emit_gap_audit_row(
        store=store,
        title="Credential required for provider A",
        rationale="Provider docs require an API key.",
        proposal_type=ProposalType.CODE_AND_DB_CHANGE,
        proposal_status=ProposalStatus.PROPOSED,
        requested_by=RequestedBy.AGENT,
        risk_level=RiskLevel.MEDIUM,
        item_type=ItemType.VALIDATION,
        target_type=TargetType.PROVIDERS,
        action=Action.VALIDATE,
        target_ref="providers/provider-a",
        proposed_data={"gap_id": "gap-1", "env_var": "PROVIDER_A_KEY"},
        validation_status=ValidationStatus.PENDING,
        validation_notes="Waiting for operator provisioning.",
    )
    second = await emit_gap_audit_row(
        store=store,
        title="Credential required for provider B",
        rationale="Provider docs require an API key.",
        proposal_type=ProposalType.CODE_AND_DB_CHANGE,
        proposal_status=ProposalStatus.PROPOSED,
        requested_by=RequestedBy.AGENT,
        risk_level=RiskLevel.MEDIUM,
        item_type=ItemType.VALIDATION,
        target_type=TargetType.PROVIDERS,
        action=Action.VALIDATE,
        target_ref="providers/provider-b",
        proposed_data={"gap_id": "gap-2", "env_var": "PROVIDER_B_KEY"},
        validation_status=ValidationStatus.PENDING,
        validation_notes="Waiting for operator provisioning.",
    )

    assert first.proposal_id == "proposal-1"
    assert second.proposal_id == "proposal-2"
    assert [proposal["title"] for proposal in store.proposals] == [
        "Credential required for provider A",
        "Credential required for provider B",
    ]
    assert store.items == [
        {
            "id": "item-1",
            "proposal_id": "proposal-1",
            "item_type": ItemType.VALIDATION,
            "target_type": TargetType.PROVIDERS,
            "action": Action.VALIDATE,
            "target_id": None,
            "target_ref": "providers/provider-a",
            "proposed_data": {"gap_id": "gap-1", "env_var": "PROVIDER_A_KEY"},
            "diff_summary": None,
            "validation_status": ValidationStatus.PENDING,
            "validation_notes": "Waiting for operator provisioning.",
        },
        {
            "id": "item-2",
            "proposal_id": "proposal-2",
            "item_type": ItemType.VALIDATION,
            "target_type": TargetType.PROVIDERS,
            "action": Action.VALIDATE,
            "target_id": None,
            "target_ref": "providers/provider-b",
            "proposed_data": {"gap_id": "gap-2", "env_var": "PROVIDER_B_KEY"},
            "diff_summary": None,
            "validation_status": ValidationStatus.PENDING,
            "validation_notes": "Waiting for operator provisioning.",
        },
    ]
