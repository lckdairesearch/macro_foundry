"""Geography-related enums."""

from enum import Enum


class GeographyType(str, Enum):
    COUNTRY = "country"
    SUBNATIONAL = "subnational"
    SUBNATIONAL_REGION = "subnational_region"
    REGION = "region"
    BLOC = "bloc"
    WORLD = "world"


class CodeStandard(str, Enum):
    ISO_3166_1 = "ISO 3166-1"
    ISO_3166_2 = "ISO 3166-2"
    WB = "WB"
    INTERNAL = "internal"


__all__ = ["CodeStandard", "GeographyType"]
