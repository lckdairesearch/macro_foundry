"""Gate 1 wait node, approval_parse, apply_small_edit, and un-approval window (issue 45)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

from macro_foundry.agent.channel import Channel, ChannelEvent
from macro_foundry.agent.proposal import DraftProposal


class GateOutcome(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    PERMIT_FURTHER_CYCLE = "permit_further_cycle"


class CollisionChoice(str, Enum):
    RENAME = "rename"
    CHALLENGE_EXISTING = "challenge_existing"
    CANCEL = "cancel"


# Picker callable: receives (options, review_cycle) → returns outcome string.
PickerCallable = Callable[..., Awaitable[str]]

# LLM callable used only in the Request changes branch for approval parsing.
ApprovalLLMCallable = Callable[..., Awaitable[dict[str, Any]]]

# Uniqueness checker: receives (proposal_dict, edit_instructions) → collision dict or None.
UniqueCheckerCallable = Callable[..., Awaitable[dict[str, Any] | None]]


def _normal_picker_options(review_cycle: int) -> list[str]:
    if review_cycle >= 3:
        return [
            GateOutcome.APPROVE.value,
            GateOutcome.REJECT.value,
            GateOutcome.PERMIT_FURTHER_CYCLE.value,
        ]
    return [
        GateOutcome.APPROVE.value,
        GateOutcome.REJECT.value,
        GateOutcome.REQUEST_CHANGES.value,
    ]


def render_gate_1_summary(
    *,
    proposal: DraftProposal,
    harmonisation_items: list[dict[str, Any]],
    suggest_human_apply_items: list[dict[str, Any]],
) -> str:
    """Render the Gate 1 proposal summary with three sections per ADR 0013."""

    lines: list[str] = ["## Gate 1 Approval\n"]

    lines.append("### New series items\n")
    lines.append(f"  Series: {proposal.series.code} — {proposal.series.name}")
    lines.append(f"  Concept: {proposal.concept.code}")
    lines.append(f"  Family: {proposal.family.code}\n")

    lines.append("### Harmonisation companion items\n")
    if harmonisation_items:
        for item in harmonisation_items:
            lines.append(f"  {item.get('series_code', '')} / {item.get('field', '')}: {item.get('proposed', '')}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("### Suggest-for-human-apply items\n")
    if suggest_human_apply_items:
        for item in suggest_human_apply_items:
            lines.append(f"  {item.get('field', '')}: {item.get('proposed', '')}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)


def make_gate_1_wait_node(
    *,
    channel: Channel,
    approval_llm: ApprovalLLMCallable,
    picker: PickerCallable,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return the gate_1_wait interrupt node.

    Renders the proposal summary, presents the structured picker, and routes:
    - Approve → sets gate_1_approved=True, no LLM call
    - Reject → records outcome, no LLM call
    - Request changes → calls approval_llm to extract edit instructions
    - Permit further cycle (cycle 3 only) → records outcome
    """

    async def _gate_1_wait_node(state: dict[str, Any]) -> dict[str, Any]:
        from macro_foundry.agent.onboarding_state import NodeTransition
        from datetime import datetime, timezone

        proposal_dict = state.get("proposal") or {}
        review_cycle = state.get("review_cycle") or 0

        # Reconstruct proposal for summary rendering
        try:
            proposal = DraftProposal.model_validate(proposal_dict)
        except Exception:
            proposal = None

        if proposal is not None:
            summary = render_gate_1_summary(
                proposal=proposal,
                harmonisation_items=state.get("harmonisation_items") or [],
                suggest_human_apply_items=state.get("suggest_human_apply_items") or [],
            )
            await channel.emit(ChannelEvent(text=summary))

        outcome_str = await picker(_normal_picker_options(review_cycle), review_cycle)

        now = datetime.now(timezone.utc)
        update: dict[str, Any] = {
            "gate_1_outcome": outcome_str,
            "node_transitions": [
                NodeTransition(node="gate_1_wait", event="completed", created_at=now).model_dump(mode="json"),
            ],
        }

        if outcome_str == GateOutcome.APPROVE.value:
            update["gate_1_approved"] = True
            update["gate_1_applied"] = False

        elif outcome_str == GateOutcome.REQUEST_CHANGES.value:
            result = await approval_llm(state)
            update["small_edit_instructions"] = result.get("edit_instructions")

        return update

    return _gate_1_wait_node


def make_apply_small_edit_node(
    *,
    unique_checker: UniqueCheckerCallable,
    collision_picker: PickerCallable | None = None,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return the apply_small_edit node.

    Applies a textual edit to the in-memory proposal, then:
    - No collision → clears gate_1_outcome so gate_1_wait re-issues the picker
    - Collision → presents a three-way choice (rename / challenge_existing / cancel)
    """

    async def _apply_small_edit_node(state: dict[str, Any]) -> dict[str, Any]:
        from macro_foundry.agent.onboarding_state import NodeTransition
        from datetime import datetime, timezone

        proposal_dict: dict[str, Any] = dict(state.get("proposal") or {})
        edit_instructions: str = state.get("small_edit_instructions") or ""

        # Apply edit to proposal dict (simple field-rename heuristic for v1)
        proposal_dict = _apply_edit_to_proposal(proposal_dict, edit_instructions)

        collision = await unique_checker(proposal_dict, edit_instructions)

        now = datetime.now(timezone.utc)
        transition = NodeTransition(node="apply_small_edit", event="completed", created_at=now).model_dump(mode="json")

        if collision is None:
            return {
                "proposal": proposal_dict,
                "gate_1_outcome": None,
                "small_edit_instructions": None,
                "node_transitions": [transition],
            }

        # Collision path — offer three-way choice
        picker = collision_picker or _default_collision_picker
        choice_str = await picker(
            [c.value for c in CollisionChoice],
            collision,
        )
        collision_update: dict[str, Any] = {
            "proposal": proposal_dict,
            "collision_choice": choice_str,
            "collision_detail": collision,
            "node_transitions": [transition],
        }
        if choice_str == CollisionChoice.CHALLENGE_EXISTING.value:
            collision_update["gate_2_escalation"] = True
        return collision_update

    return _apply_small_edit_node


def _apply_edit_to_proposal(proposal: dict[str, Any], instructions: str) -> dict[str, Any]:
    """Apply a small textual edit instruction to the proposal dict (v1 heuristic).

    The approval_parse LLM is responsible for producing structured instructions;
    this function applies them. For v1, instructions are expected as
    'rename <dotted.path> to <value>' or accepted verbatim as a JSON patch.
    Unrecognised instructions are a no-op — the pre-check will catch any
    semantic issues.
    """
    import copy
    import re

    result = copy.deepcopy(proposal)

    # Pattern: "rename <path> to <value>"
    m = re.match(r"rename\s+([\w.]+)\s+(?:code\s+)?to\s+(.+)", instructions, re.IGNORECASE)
    if m:
        path_str, new_value = m.group(1).strip(), m.group(2).strip()
        _set_nested(result, path_str.split("."), new_value)

    return result


def _set_nested(d: dict[str, Any], keys: list[str], value: Any) -> None:
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    if keys:
        d[keys[-1]] = value


def make_unapprove_node() -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return the unapprove node for the un-approval window.

    Allowed only while gate_1_applied is False. After apply_catalog writes,
    revocation becomes a correction proposal and this node rejects the attempt.
    """

    async def _unapprove_node(state: dict[str, Any]) -> dict[str, Any]:
        from macro_foundry.agent.onboarding_state import NodeTransition
        from datetime import datetime, timezone

        already_applied = state.get("gate_1_applied") is True
        if already_applied:
            return {
                "gate_1_approved": True,
                "unapprove_rejected": True,
                "node_transitions": [
                    NodeTransition(node="unapprove", event="rejected_post_apply", created_at=datetime.now(timezone.utc)).model_dump(mode="json"),
                ],
            }

        return {
            "gate_1_approved": False,
            "gate_1_outcome": None,
            "node_transitions": [
                NodeTransition(node="unapprove", event="completed", created_at=datetime.now(timezone.utc)).model_dump(mode="json"),
            ],
        }

    return _unapprove_node


_STRUCTURAL_KEYWORDS: frozenset[str] = frozenset({
    "frequency",
    "methodology",
    "hierarchy",
    "edge",
    "selector",
    "config",
    "configuration",
    "measure",
    "unit",
    "seasonal",
    "adjustment",
})


def is_structural_edit(instructions: str) -> bool:
    """Return True when edit instructions touch structural fields.

    Structural edits route back through the full drafter cycle (issue 45).
    Textual edits (name, description, code rename) route through apply_small_edit.
    """
    lower = instructions.lower()
    return any(keyword in lower for keyword in _STRUCTURAL_KEYWORDS)


async def _default_collision_picker(options: list[str], collision: dict[str, Any]) -> str:
    """Fallback collision picker — raises to force injection in tests."""
    raise RuntimeError("collision_picker must be injected; use make_apply_small_edit_node(collision_picker=...)")


__all__ = [
    "CollisionChoice",
    "GateOutcome",
    "PickerCallable",
    "UniqueCheckerCallable",
    "is_structural_edit",
    "make_apply_small_edit_node",
    "make_gate_1_wait_node",
    "make_unapprove_node",
    "render_gate_1_summary",
]
