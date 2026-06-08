"""Derived-series and computation enums."""

from enum import Enum


class ExecutionPolicy(str, Enum):
    SCHEDULED = "scheduled"
    UPSTREAM_UPDATE = "upstream_update"
    MANUAL = "manual"


class InputVintagePolicy(str, Enum):
    LATEST_AVAILABLE = "latest_available"
    VINTAGE_AS_OF = "vintage_as_of"
    FIXED_VINTAGE = "fixed_vintage"
    WINDOW_RELATIVE = "window_relative"


class OutputMode(str, Enum):
    WRITE_OBSERVATIONS = "write_observations"
    DRY_RUN = "dry_run"
    VALIDATION_ONLY = "validation_only"


__all__ = ["ExecutionPolicy", "InputVintagePolicy", "OutputMode"]
