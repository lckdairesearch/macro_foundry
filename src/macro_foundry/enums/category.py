"""Category-tree enums."""

from enum import Enum


class CategoryKind(str, Enum):
    """Discriminator for a node in the single `categories` tree (ADR 0025 §1)."""

    TOPIC = "topic"  # browse/navigation node (PRICES); not attachable by a series
    CONCEPT = "concept"  # attachable economic idea (CPI_ALL_ITEMS); the old concept grain


__all__ = ["CategoryKind"]
