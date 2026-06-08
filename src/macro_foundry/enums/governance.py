"""Governance workflow enums."""

from enum import Enum


class ProposalType(str, Enum):
    ADD_PROVIDER_SERIES = "add_provider_series"
    ADD_DERIVED_SERIES = "add_derived_series"
    ADD_FAMILY = "add_family"
    ADD_CONCEPT = "add_concept"
    CODE_AND_DB_CHANGE = "code_and_db_change"
    SCHEMA_CHANGE = "schema_change"
    MIXED = "mixed"


class ProposalStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class RequestedBy(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ItemType(str, Enum):
    DB_ROW = "db_row"
    CODE_CHANGE = "code_change"
    MIGRATION = "migration"
    TEST = "test"
    VALIDATION = "validation"
    DOCUMENTATION = "documentation"


class TargetType(str, Enum):
    CONCEPTS = "concepts"
    SERIES = "series"
    SERIES_FAMILIES = "series_families"
    SERIES_SOURCES = "series_sources"
    INGESTION_FEEDS = "ingestion_feeds"
    FILE = "file"
    FUNCTION = "function"
    TEST = "test"
    PROVIDERS = "providers"
    PROVIDER_CATALOGS = "provider_catalogs"
    DERIVED_SERIES = "derived_series"
    DERIVATION_INPUTS = "derivation_inputs"
    GEOGRAPHIES = "geographies"
    TAGS = "tags"
    SERIES_FAMILY_MEMBERS = "series_family_members"
    GEOGRAPHY_MEMBERSHIPS = "geography_memberships"


class Action(str, Enum):
    INSERT = "insert"
    UPDATE = "update"
    DEACTIVATE = "deactivate"
    CREATE_FILE = "create_file"
    MODIFY_FILE = "modify_file"
    RUN_TEST = "run_test"
    VALIDATE = "validate"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    NOT_REQUIRED = "not_required"


__all__ = [
    "Action",
    "ItemType",
    "ProposalStatus",
    "ProposalType",
    "RequestedBy",
    "RiskLevel",
    "TargetType",
    "ValidationStatus",
]
