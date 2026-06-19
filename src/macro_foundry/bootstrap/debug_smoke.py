"""Request-centric debug smoke bootstrap — disabled pending V8 rebootstrap.

The smoke set built the V7 conceptual spine (concept / indicator /
indicator_variant) that ADR 0025 dropped. A categories-aware replacement is part
of the V8 rebootstrap slice; the previous implementation is preserved in git
history. The public API is kept so importers stay valid.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from macro_foundry.db import EnvTarget

_DEFERRED_MESSAGE = (
    "The debug smoke bootstrap is disabled pending the V8 rebootstrap slice "
    "(ADR 0025): it built the dropped concept/indicator/variant spine."
)


@dataclass(frozen=True, slots=True)
class DebugSmokeBootstrapResult:
    """Summary of the request-centric debug bootstrap."""

    target: EnvTarget
    run_date: date
    feed_members: int
    member_logs: int
    observations: int
    hierarchy_edges: int


async def run_debug_smoke_bootstrap(*args: Any, **kwargs: Any) -> DebugSmokeBootstrapResult:
    raise NotImplementedError(_DEFERRED_MESSAGE)


__all__ = ["DebugSmokeBootstrapResult", "run_debug_smoke_bootstrap"]
