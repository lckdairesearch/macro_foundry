"""Shared seed-run bookkeeping helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(slots=True)
class SeedOutcome:
    """Simple inserted/updated counters for one seed target."""

    inserted: int = 0
    updated: int = 0

    def absorb(self, other: "SeedOutcome") -> None:
        self.inserted += other.inserted
        self.updated += other.updated


def assign_if_changed(instance: Any, values: Mapping[str, Any], fields: Sequence[str]) -> bool:
    """Assign fields on an ORM instance when seed data differs."""

    changed = False
    for field in fields:
        new_value = values[field]
        if getattr(instance, field) != new_value:
            setattr(instance, field, new_value)
            changed = True
    return changed


__all__ = ["SeedOutcome", "assign_if_changed"]
