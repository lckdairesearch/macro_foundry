"""Provider-related enums."""

from enum import Enum


class ProviderType(str, Enum):
    OFFICIAL = "official"
    INTERNATIONAL_ORGANIZATION = "international_organization"
    VENDOR = "vendor"
    INTERNAL = "internal"
    OTHER = "other"


class AuthScheme(str, Enum):
    BEARER_HEADER = "bearer_header"
    QUERY_PARAM = "query_param"
    HEADER_CUSTOM = "header_custom"
    BASIC_AUTH = "basic_auth"
    NONE = "none"


class ProviderRole(str, Enum):
    PRIMARY_SOURCE = "primary_source"
    REDISTRIBUTOR = "redistributor"
    HARMONIZED = "harmonized"
    VENDOR_ESTIMATE = "vendor_estimate"
    INTERNAL = "internal"
    OTHER = "other"


class FeedMethod(str, Enum):
    API = "api"
    FILE = "file"
    SCRAPE = "scrape"


class SourceGroupType(str, Enum):
    """Kind of provider-side publication unit (ADR 0025 §4)."""

    RELEASE = "release"
    TABLE = "table"
    DATASET = "dataset"
    DASHBOARD = "dashboard"
    OTHER = "other"


__all__ = ["AuthScheme", "FeedMethod", "ProviderRole", "ProviderType", "SourceGroupType"]
