"""Pause/resume lifecycle helpers for escalation wait nodes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from inspect import isawaitable
from typing import Any

from pydantic import BaseModel, ConfigDict


class PauseExit(BaseModel):
    """Clean CLI-exit decision after checkpointed operator pause."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    checkpoint_position: str | None
    exit_code: int = 0


class GapVerification(BaseModel):
    """Result returned by a gap-specific verifier during resume."""

    model_config = ConfigDict(frozen=True)

    gap_id: str
    resolved: bool
    resolution: dict[str, Any] | None = None


class ResumeWalkResult(BaseModel):
    """State returned after walking pending gaps on resume."""

    model_config = ConfigDict(frozen=True)

    state: dict[str, Any]
    all_resolved: bool
    pending_gap_ids: tuple[str, ...] = ()


GapVerifier = Callable[[dict[str, Any]], GapVerification | Awaitable[GapVerification]]


def pause_and_exit(state: Mapping[str, Any]) -> PauseExit:
    """Return a clean exit decision without advancing the checkpoint position."""

    return PauseExit(
        session_id=str(state["session_id"]),
        checkpoint_position=state.get("checkpoint_position"),
    )


async def resume_walk(
    state: Mapping[str, Any],
    verifier: GapVerifier,
    *,
    gap_field: str,
    resolution_field: str,
) -> ResumeWalkResult:
    """Verify unresolved gaps and append gap-kind-specific resolutions."""

    next_state = deepcopy(dict(state))
    gaps = [_dict_gap(gap) for gap in next_state.get(gap_field, ())]
    resolutions = [_dict_gap(resolution) for resolution in next_state.get(resolution_field, ())]
    resolved_gap_ids = {str(resolution["gap_id"]) for resolution in resolutions}
    pending_gap_ids: list[str] = []

    for gap in gaps:
        gap_id = str(gap["gap_id"])
        if gap_id in resolved_gap_ids:
            continue

        verification = verifier(gap)
        if isawaitable(verification):
            verification = await verification

        if verification.resolved:
            if verification.resolution is None:
                raise ValueError("resolved gap verification must include a resolution")
            resolutions.append(verification.resolution)
            resolved_gap_ids.add(gap_id)
        else:
            pending_gap_ids.append(gap_id)

    next_state[resolution_field] = resolutions
    return ResumeWalkResult(
        state=next_state,
        all_resolved=not pending_gap_ids,
        pending_gap_ids=tuple(pending_gap_ids),
    )


def _dict_gap(gap: Any) -> dict[str, Any]:
    if isinstance(gap, BaseModel):
        return gap.model_dump(mode="json")
    if isinstance(gap, dict):
        return gap
    raise TypeError("gaps and resolutions must be dicts or Pydantic models")


__all__ = [
    "GapVerification",
    "GapVerifier",
    "PauseExit",
    "ResumeWalkResult",
    "pause_and_exit",
    "resume_walk",
]
