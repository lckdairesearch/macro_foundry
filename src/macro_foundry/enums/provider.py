"""Provider-related enums."""

from enum import Enum


class ProviderType(str, Enum):
    OFFICIAL = "official"
    INTERNATIONAL_ORGANIZATION = "international_organization"
    VENDOR = "vendor"
    INTERNAL = "internal"
    OTHER = "other"


class ProviderRole(str, Enum):
    PRIMARY_SOURCE = "primary_source"
    REDISTRIBUTOR = "redistributor"
    HARMONIZED = "harmonized"
    VENDOR_ESTIMATE = "vendor_estimate"
    INTERNAL = "internal"
    OTHER = "other"


class FeedMethod(str, Enum):
    API = "api"
    FILE_UPLOAD = "file_upload"


__all__ = ["FeedMethod", "ProviderRole", "ProviderType"]
