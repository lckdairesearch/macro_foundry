"""Series-related enums."""

from enum import Enum


class OriginType(str, Enum):
    INGESTED = "ingested"
    DERIVED = "derived"
    BOTH = "both"


class Frequency(str, Enum):
    DAILY = "D"
    WEEKLY = "W"
    MONTHLY = "M"
    QUARTERLY = "Q"
    SEMI_ANNUAL = "S"
    ANNUAL = "A"


class TemporalStockFlow(str, Enum):
    STOCK = "stock"
    FLOW = "flow"
    RATE = "rate"
    INDEX = "index"
    UNKNOWN = "unknown"


class UnitKind(str, Enum):
    INDEX = "index"
    PERCENT = "percent"
    BPS = "bps"
    CURRENCY = "currency"
    COUNT = "count"
    QUANTITY = "quantity"
    RATIO = "ratio"
    NONE = "none"


class UnitScale(str, Enum):
    ONE = "one"
    THOUSAND = "thousand"
    MILLION = "million"
    BILLION = "billion"
    TRILLION = "trillion"


class PriceBasis(str, Enum):
    NOMINAL = "nominal"
    REAL = "real"
    PPP = "ppp"
    OTHER = "other"


class Measure(str, Enum):
    LEVEL = "level"
    GROWTH = "growth"
    CHANGE = "change"


class MeasureHorizon(str, Enum):
    YTD = "ytd"
    WOW = "wow"
    MOM = "mom"
    QOQ = "qoq"
    YOY = "yoy"
    CUSTOM = "custom"


class SeasonalAdjustment(str, Enum):
    SA = "SA"
    SAAR = "SAAR"
    NSA = "NSA"
    UNKNOWN = "unknown"


class ReferenceKind(str, Enum):
    INDEX_BASE = "index_base"
    CONSTANT_PRICES = "constant_prices"
    PPP_BASE = "ppp_base"
    OTHER = "other"


__all__ = [
    "Frequency",
    "Measure",
    "MeasureHorizon",
    "OriginType",
    "PriceBasis",
    "ReferenceKind",
    "SeasonalAdjustment",
    "TemporalStockFlow",
    "UnitKind",
    "UnitScale",
]
