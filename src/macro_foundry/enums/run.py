"""Run-log enums split by table so CHECK constraints match V3 exactly."""

from enum import Enum

_SUCCESS = "success"
_FAILED = "failed"
_PARTIAL = "partial"
_SCHEDULER = "scheduler"
_MANUAL = "manual"
_BACKFILL = "backfill"


class IngestionRunStatus(str, Enum):
    SUCCESS = _SUCCESS
    FAILED = _FAILED
    PARTIAL = _PARTIAL


class ComputationRunStatus(str, Enum):
    SUCCESS = _SUCCESS
    FAILED = _FAILED
    PARTIAL = _PARTIAL
    PENDING = "pending"


class IngestionTriggeredBy(str, Enum):
    SCHEDULER = _SCHEDULER
    MANUAL = _MANUAL
    BACKFILL = _BACKFILL


class ComputationTriggeredBy(str, Enum):
    SCHEDULER = _SCHEDULER
    MANUAL = _MANUAL
    BACKFILL = _BACKFILL
    UPSTREAM_UPDATE = "upstream_update"


__all__ = [
    "ComputationRunStatus",
    "ComputationTriggeredBy",
    "IngestionRunStatus",
    "IngestionTriggeredBy",
]
