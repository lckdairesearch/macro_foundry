"""Shared Pydantic schema helpers."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

BASE_MODEL_CONFIG = ConfigDict(extra="forbid")
READ_MODEL_CONFIG = ConfigDict(from_attributes=True, extra="forbid")


class SchemaModel(BaseModel):
    """Base schema with strict field handling."""

    model_config = BASE_MODEL_CONFIG


class ReadSchema(SchemaModel):
    """Base schema for read models validated from ORM objects."""

    model_config = READ_MODEL_CONFIG


class CreatedAtReadSchema(ReadSchema):
    """Shared read fields for append-only tables."""

    id: UUID
    created_at: datetime


class TimestampedReadSchema(CreatedAtReadSchema):
    """Shared read fields for mutable tables."""

    updated_at: datetime


__all__ = [
    "BASE_MODEL_CONFIG",
    "CreatedAtReadSchema",
    "READ_MODEL_CONFIG",
    "ReadSchema",
    "SchemaModel",
    "TimestampedReadSchema",
]
