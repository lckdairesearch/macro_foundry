"""Enum-gap wait node helpers for onboarding sessions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from importlib import import_module
from inspect import isawaitable
from typing import Any

from macro_foundry.agent.escalation.picker import (
    EscalationPickerOption,
    EscalationPickerResult,
    OperatorInstructionBlock,
    PickerOutcome,
    render_escalation_picker,
)
from macro_foundry.agent.onboarding_state import EnumGapProposal

PickerCallable = Callable[..., EscalationPickerResult | Awaitable[EscalationPickerResult]]
EnumValuesCallable = Callable[..., set[str] | Awaitable[set[str]]]
CoerceResolver = Callable[[dict[str, Any]], tuple[str, str] | Awaitable[tuple[str, str]]]
RenameReconciler = Callable[[dict[str, Any], str], bool | Awaitable[bool]]

_ENUM_TARGETS: dict[str, tuple[str, str]] = {
    "macro_foundry.enums.series.Frequency": ("series", "frequency"),
    "macro_foundry.enums.series.SeasonalAdjustment": ("series", "seasonal_adjustment"),
    "macro_foundry.enums.series.Measure": ("series", "measure"),
    "macro_foundry.enums.series.MeasureHorizon": ("series", "measure_horizon"),
    "macro_foundry.enums.series.UnitKind": ("series", "unit_kind"),
    "macro_foundry.enums.series.UnitScale": ("series", "unit_scale"),
    "macro_foundry.enums.series.PriceBasis": ("series", "price_basis"),
    "macro_foundry.enums.series.ReferenceKind": ("series", "reference_kind"),
    "macro_foundry.enums.series.TemporalStockFlow": ("series", "temporal_stock_flow"),
}


def build_enum_gap_instruction_blocks(
    *,
    gap: dict[str, Any],
    session_id: str,
) -> tuple[OperatorInstructionBlock, ...]:
    """Render ADR 0014 operator instructions for one enum gap."""

    proposal = EnumGapProposal.model_validate(gap)
    table, column = _target_table_column(proposal.enum_path)
    enum_class = proposal.enum_path.rsplit(".", 1)[1]
    existing_values = tuple(proposal.existing_values_considered)
    widened_values = (*existing_values, proposal.proposed_value)

    diff = (
        f"src/macro_foundry/enums/series.py\n"
        f"class {enum_class}(str, Enum):\n"
        f'+    {proposal.proposed_name} = "{proposal.proposed_value}"'
    )
    migration = (
        "def upgrade() -> None:\n"
        f'    op.drop_constraint("ck_{table}_{column}", "{table}", type_="check")\n'
        "    op.create_check_constraint(\n"
        f'        "ck_{table}_{column}", "{table}",\n'
        f'        "{column} IN ({_sql_literal_list(widened_values)})",\n'
        "    )\n\n"
        "def downgrade() -> None:\n"
        f'    op.drop_constraint("ck_{table}_{column}", "{table}", type_="check")\n'
        "    op.create_check_constraint(\n"
        f'        "ck_{table}_{column}", "{table}",\n'
        f'        "{column} IN ({_sql_literal_list(existing_values)})",\n'
        "    )"
    )
    resume = f"After editing Python and applying the Alembic migration, run:\nmacrodb onboard --resume {session_id}"

    return (
        OperatorInstructionBlock(title="Enum gap", body=_gap_summary(proposal)),
        OperatorInstructionBlock(title="Python enum diff", body=diff),
        OperatorInstructionBlock(title="Alembic migration template", body=migration),
        OperatorInstructionBlock(title="Resume command", body=resume),
    )


def make_enum_gap_wait_node(
    *,
    picker: PickerCallable = render_escalation_picker,
    python_enum_values: EnumValuesCallable = lambda enum_path: _python_enum_values(enum_path),
    db_enum_values: EnumValuesCallable | None = None,
    coerce_resolver: CoerceResolver | None = None,
    rename_reconciler: RenameReconciler | None = None,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return the enum_gap_wait node with injectable operator and verification seams."""

    async def _enum_gap_wait_node(state: dict[str, Any]) -> dict[str, Any]:
        gaps = [EnumGapProposal.model_validate(gap).model_dump(mode="json") for gap in state.get("enum_gap_proposals", [])]
        resolutions = list(state.get("enum_gap_resolutions") or [])
        resolved_ids = {_gap_id(resolution) for resolution in resolutions}
        pending_gaps = [gap for gap in gaps if _gap_id(gap) not in resolved_ids]

        verified = await _verify_pending_gaps(
            pending_gaps,
            python_enum_values=python_enum_values,
            db_enum_values=db_enum_values,
            rename_reconciler=rename_reconciler,
        )
        resolutions.extend(verified)
        resolved_ids.update(_gap_id(resolution) for resolution in verified)
        pending_gaps = [gap for gap in pending_gaps if _gap_id(gap) not in resolved_ids]

        if not pending_gaps:
            return {
                "enum_gap_proposals": [],
                "enum_gap_resolutions": resolutions,
                "node_transitions": [_transition("enum_gap_wait", "resolved")],
            }

        session_id = _session_id(state)
        selected = await _maybe_await(
            picker(
                prompt="Enum value missing",
                options=(
                    EscalationPickerOption(label="Apply later (pause)", outcome=PickerOutcome.APPLY_LATER),
                    EscalationPickerOption(label="Decline and coerce", outcome=PickerOutcome.DECLINE_AND_COERCE),
                    EscalationPickerOption(label="Abort", outcome=PickerOutcome.ABORT),
                ),
                instruction_blocks=build_enum_gap_instruction_blocks(gap=pending_gaps[0], session_id=session_id),
            )
        )

        if selected.outcome is PickerOutcome.APPLY_LATER:
            return {
                "checkpoint_position": "enum_gap_wait",
                "enum_gap_resolutions": resolutions,
                "node_transitions": [_transition("enum_gap_wait", "paused")],
            }

        if selected.outcome is PickerOutcome.DECLINE_AND_COERCE:
            if coerce_resolver is None:
                raise ValueError("Decline and coerce requires coerce_resolver")
            coerce_hints = dict(state.get("coerce_hints") or {})
            coerce_rationales = dict(state.get("coerce_rationales") or {})
            for gap in pending_gaps:
                value, rationale = await _maybe_await(coerce_resolver(gap))
                coerce_hints[gap["enum_path"]] = value
                coerce_rationales[gap["enum_path"]] = rationale
                resolutions.append(
                    {
                        "gap_id": _gap_id(gap),
                        "enum_path": gap["enum_path"],
                        "outcome": "declined_coerce",
                        "applied_value": value,
                        "operator_rationale": rationale,
                        "resolved_at": _now_iso(),
                    }
                )
            return {
                "enum_gap_proposals": [],
                "enum_gap_resolutions": resolutions,
                "coerce_hints": coerce_hints,
                "coerce_rationales": coerce_rationales,
                "node_transitions": [_transition("enum_gap_wait", "declined_coerce")],
            }

        return {
            "abort_reason": "enum_gap_declined",
            "enum_gap_resolutions": [
                *resolutions,
                *[
                    {
                        "gap_id": _gap_id(gap),
                        "enum_path": gap["enum_path"],
                        "outcome": "aborted",
                        "applied_value": None,
                        "operator_rationale": "Operator aborted enum-gap session.",
                        "resolved_at": _now_iso(),
                    }
                    for gap in pending_gaps
                ],
            ],
            "node_transitions": [_transition("enum_gap_wait", "aborted")],
        }

    return _enum_gap_wait_node


async def _verify_pending_gaps(
    gaps: list[dict[str, Any]],
    *,
    python_enum_values: EnumValuesCallable,
    db_enum_values: EnumValuesCallable | None,
    rename_reconciler: RenameReconciler | None,
) -> list[dict[str, Any]]:
    if db_enum_values is None:
        return []

    resolutions: list[dict[str, Any]] = []
    for gap in gaps:
        table, column = _target_table_column(gap["enum_path"])
        python_values = await _maybe_await(python_enum_values(gap["enum_path"]))
        db_values = await _maybe_await(db_enum_values(table, column))
        proposed_value = gap["proposed_value"]

        if proposed_value in python_values and proposed_value in db_values:
            resolutions.append(_resolution(gap, outcome="applied", applied_value=proposed_value))
            continue

        existing_values = set(gap["existing_values_considered"])
        renamed_candidates = (python_values & db_values) - existing_values - {proposed_value}
        if len(renamed_candidates) == 1 and rename_reconciler is not None:
            candidate = next(iter(renamed_candidates))
            accepted = await _maybe_await(rename_reconciler(gap, candidate))
            if accepted:
                resolutions.append(_resolution(gap, outcome="applied_renamed", applied_value=candidate))

    return resolutions


def _resolution(gap: dict[str, Any], *, outcome: str, applied_value: str) -> dict[str, Any]:
    return {
        "gap_id": _gap_id(gap),
        "enum_path": gap["enum_path"],
        "outcome": outcome,
        "applied_value": applied_value,
        "operator_rationale": None,
        "resolved_at": _now_iso(),
    }


def _python_enum_values(enum_path: str) -> set[str]:
    module_name, class_name = enum_path.rsplit(".", 1)
    module = import_module(module_name)
    enum_class = getattr(module, class_name)
    return {member.value for member in enum_class}


def _target_table_column(enum_path: str) -> tuple[str, str]:
    try:
        return _ENUM_TARGETS[enum_path]
    except KeyError as exc:
        raise ValueError(f"Unsupported enum gap path: {enum_path}") from exc


def _gap_summary(proposal: EnumGapProposal) -> str:
    return (
        f"{proposal.enum_path}\n"
        f"Proposed: {proposal.proposed_name} = {proposal.proposed_value}\n"
        f"Rationale: {proposal.rationale}\n"
        f"Evidence: {proposal.provider_evidence.url} - {proposal.provider_evidence.snippet}\n"
        f"Catalog impact: {proposal.catalog_impact}"
    )


def _sql_literal_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _session_id(state: dict[str, Any]) -> str:
    metadata = state.get("session_metadata") or {}
    return str(metadata.get("session_id") or state.get("session_id") or "<session-id>")


def _gap_id(gap: dict[str, Any]) -> str:
    return str(gap.get("gap_id") or f"{gap['enum_path']}:{gap.get('proposed_value') or gap.get('applied_value')}")


def _transition(node: str, event: str) -> dict[str, Any]:
    return {
        "node": node,
        "event": event,
        "created_at": _now_iso(),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


__all__ = [
    "build_enum_gap_instruction_blocks",
    "make_enum_gap_wait_node",
]
