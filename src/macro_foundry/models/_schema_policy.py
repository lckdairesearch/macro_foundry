"""Private helpers for repeated ORM schema policy."""

from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import MappedColumn, mapped_column


def enum_column(
    table_name: str,
    column_name: str,
    enum_type: type[Enum],
    *,
    nullable: bool,
) -> MappedColumn[Any]:
    """Build a CHECK-constrained enum column with the canonical naming policy."""

    return mapped_column(
        SAEnum(
            enum_type,
            native_enum=False,
            name=f"ck_{table_name}_{column_name}",
            validate_strings=True,
        ),
        nullable=nullable,
    )


def fk_uuid(
    target: str,
    *,
    ondelete: str,
    nullable: bool,
) -> MappedColumn[Any]:
    """Build a UUID foreign-key column with explicit delete behavior."""

    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
    )


__all__ = ["enum_column", "fk_uuid"]
