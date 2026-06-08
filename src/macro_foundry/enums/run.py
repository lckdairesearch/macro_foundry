"""Run-log enums."""

from enum import Enum


class RunStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    PENDING = "pending"


class TriggeredBy(str, Enum):
    SCHEDULER = "scheduler"
    MANUAL = "manual"
    BACKFILL = "backfill"
    UPSTREAM_UPDATE = "upstream_update"


__all__ = ["RunStatus", "TriggeredBy"]
