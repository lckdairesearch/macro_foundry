"""Governance workflow enums."""

from enum import Enum


class ProposalType(str, Enum):
    ADD_PROVIDER_SERIES = "add_provider_series"
    ADD_DERIVED_SERIES = "add_derived_series"
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
    SERIES = "series"
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
    GEOGRAPHY_MEMBERSHIPS = "geography_memberships"
    CREDENTIAL_REF = "credential_ref"
    ENUM_VALUE = "enum_value"


class Action(str, Enum):
    INSERT = "insert"
    UPDATE = "update"
    DEACTIVATE = "deactivate"
    CREATE_FILE = "create_file"
    MODIFY_FILE = "modify_file"
    RUN_TEST = "run_test"
    VALIDATE = "validate"
    SUGGEST_HUMAN_APPLY = "suggest_human_apply"
    SUGGEST_CREDENTIAL_PROVISIONING = "suggest_credential_provisioning"
    SUGGEST_ENUM_ADDITION = "suggest_enum_addition"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    NOT_REQUIRED = "not_required"
    PENDING_HUMAN_APPLY = "pending_human_apply"
    APPLIED_BY_OPERATOR = "applied_by_operator"
    DECLINED_BY_OPERATOR = "declined_by_operator"


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
