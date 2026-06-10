"""Tests for enum-gap wait node behavior."""

from __future__ import annotations

from typing import Any

import pytest

from macro_foundry.agent.escalation.picker import (
    EscalationPickerResult,
    OperatorInstructionBlock,
    PickerOutcome,
)
from macro_foundry.agent.enum_gap import (
    build_enum_gap_instruction_blocks,
    make_enum_gap_wait_node,
)


def _gap() -> dict[str, Any]:
    return {
        "enum_path": "macro_foundry.enums.series.SeasonalAdjustment",
        "proposed_value": "TCA",
        "proposed_name": "TREND_CYCLE_ADJUSTED",
        "existing_values_considered": {
            "SA": "Seasonally adjusted is not the trend-cycle component.",
            "SAAR": "Annualized seasonal adjustment is not the trend-cycle component.",
            "NSA": "Unadjusted data is not the trend-cycle component.",
            "unknown": "Provider documentation is explicit, not unknown.",
        },
        "provider_evidence": {
            "url": "https://example.test/provider-methodology",
            "snippet": "Trend-cycle adjusted series are published separately.",
        },
        "catalog_impact": "Queries for seasonally adjusted data must not include trend-cycle data.",
        "rationale": "Provider publishes trend-cycle adjusted data as a distinct methodology.",
    }


@pytest.mark.no_db
def test_enum_gap_instruction_blocks_render_diff_migration_and_resume_command() -> None:
    blocks = build_enum_gap_instruction_blocks(
        gap=_gap(),
        session_id="sess-123",
    )
    rendered = "\n\n".join(block.render() for block in blocks)

    assert "class SeasonalAdjustment" in rendered
    assert '+    TREND_CYCLE_ADJUSTED = "TCA"' in rendered
    assert 'op.drop_constraint("ck_series_seasonal_adjustment", "series", type_="check")' in rendered
    assert "seasonal_adjustment IN ('SA', 'SAAR', 'NSA', 'unknown', 'TCA')" in rendered
    assert "macrodb onboard --resume sess-123" in rendered


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_enum_gap_wait_apply_later_sets_checkpoint_position_and_uses_three_option_picker() -> None:
    picker_calls: list[dict[str, Any]] = []

    async def picker(
        *,
        prompt: str,
        options: tuple[Any, ...],
        instruction_blocks: tuple[OperatorInstructionBlock, ...],
    ) -> EscalationPickerResult:
        picker_calls.append(
            {
                "prompt": prompt,
                "labels": [option.label for option in options],
                "blocks": instruction_blocks,
            }
        )
        return EscalationPickerResult(
            label="Apply later (pause)",
            outcome=PickerOutcome.APPLY_LATER,
        )

    node = make_enum_gap_wait_node(picker=picker)
    result = await node({
        "session_metadata": {"session_id": "sess-123"},
        "enum_gap_proposals": [_gap()],
        "enum_gap_resolutions": [],
    })

    assert result["checkpoint_position"] == "enum_gap_wait"
    assert picker_calls[0]["labels"] == [
        "Apply later (pause)",
        "Decline and coerce",
        "Abort",
    ]
    assert "macrodb onboard --resume sess-123" in picker_calls[0]["blocks"][-1].render()


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_enum_gap_wait_resume_requires_python_and_db_values_before_applied() -> None:
    async def python_values(enum_path: str) -> set[str]:
        assert enum_path == "macro_foundry.enums.series.SeasonalAdjustment"
        return {"SA", "SAAR", "NSA", "unknown", "TCA"}

    async def db_values(table: str, column: str) -> set[str]:
        assert (table, column) == ("series", "seasonal_adjustment")
        return {"SA", "SAAR", "NSA", "unknown"}

    node = make_enum_gap_wait_node(
        picker=lambda **kwargs: EscalationPickerResult(
            label="Apply later (pause)",
            outcome=PickerOutcome.APPLY_LATER,
        ),
        python_enum_values=python_values,
        db_enum_values=db_values,
    )
    result = await node({
        "session_metadata": {"session_id": "sess-123"},
        "enum_gap_proposals": [_gap()],
        "enum_gap_resolutions": [],
    })

    assert result["checkpoint_position"] == "enum_gap_wait"
    assert result.get("enum_gap_resolutions", []) == []


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_enum_gap_wait_resume_records_applied_when_python_and_db_agree() -> None:
    async def values(*args: str) -> set[str]:
        return {"SA", "SAAR", "NSA", "unknown", "TCA"}

    node = make_enum_gap_wait_node(
        picker=lambda **kwargs: EscalationPickerResult(label="Abort", outcome=PickerOutcome.ABORT),
        python_enum_values=values,
        db_enum_values=values,
    )
    result = await node({
        "session_metadata": {"session_id": "sess-123"},
        "enum_gap_proposals": [_gap()],
        "enum_gap_resolutions": [],
    })

    assert result["enum_gap_resolutions"][0]["outcome"] == "applied"
    assert result["enum_gap_resolutions"][0]["applied_value"] == "TCA"
    assert result["enum_gap_proposals"] == []


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_enum_gap_wait_decline_and_coerce_populates_hints_and_resolution() -> None:
    async def picker(**kwargs: Any) -> EscalationPickerResult:
        return EscalationPickerResult(
            label="Decline and coerce",
            outcome=PickerOutcome.DECLINE_AND_COERCE,
        )

    async def coerce_resolver(gap: dict[str, Any]) -> tuple[str, str]:
        return ("SA", "Operator treats provider trend-cycle as SA for catalog queries.")

    node = make_enum_gap_wait_node(picker=picker, coerce_resolver=coerce_resolver)
    result = await node({
        "session_metadata": {"session_id": "sess-123"},
        "enum_gap_proposals": [_gap()],
        "enum_gap_resolutions": [],
    })

    assert result["coerce_hints"] == {"macro_foundry.enums.series.SeasonalAdjustment": "SA"}
    assert result["coerce_rationales"] == {
        "macro_foundry.enums.series.SeasonalAdjustment": "Operator treats provider trend-cycle as SA for catalog queries."
    }
    assert result["enum_gap_resolutions"][0]["outcome"] == "declined_coerce"


@pytest.mark.no_db
@pytest.mark.asyncio
async def test_enum_gap_wait_reconciles_operator_renamed_value() -> None:
    async def values(*args: str) -> set[str]:
        return {"SA", "SAAR", "NSA", "unknown", "trend_cycle"}

    async def reconcile(gap: dict[str, Any], candidate_value: str) -> bool:
        assert candidate_value == "trend_cycle"
        return True

    node = make_enum_gap_wait_node(
        picker=lambda **kwargs: EscalationPickerResult(label="Abort", outcome=PickerOutcome.ABORT),
        python_enum_values=values,
        db_enum_values=values,
        rename_reconciler=reconcile,
    )
    result = await node({
        "session_metadata": {"session_id": "sess-123"},
        "enum_gap_proposals": [_gap()],
        "enum_gap_resolutions": [],
    })

    assert result["enum_gap_resolutions"][0]["outcome"] == "applied_renamed"
    assert result["enum_gap_resolutions"][0]["applied_value"] == "trend_cycle"
