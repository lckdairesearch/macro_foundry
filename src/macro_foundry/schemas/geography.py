"""Geography-domain Pydantic schemas."""

from __future__ import annotations

from datetime import date
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from macro_foundry.enums import CodeStandard, GeographyType
from macro_foundry.schemas._base import SchemaModel, TimestampedReadSchema

_PARENT_REQUIRED_TYPES = {
    GeographyType.SUBNATIONAL,
    GeographyType.SUBNATIONAL_REGION,
}


def _validate_parent_requirement(
    geography_type: GeographyType | None,
    parent_geography_id: UUID | None,
) -> None:
    if geography_type in _PARENT_REQUIRED_TYPES and parent_geography_id is None:
        raise ValueError("parent_geography_id is required for subnational geographies")


class GeographyBase(SchemaModel):
    """Shared geography fields."""

    code: str
    name: str
    alt_name: list[str] | None = None
    type: GeographyType
    code_standard: CodeStandard
    parent_geography_id: UUID | None = None
    notes: str | None = None


class GeographyCreate(GeographyBase):
    """Payload for creating a geography."""

    @model_validator(mode="after")
    def validate_parent_requirement(self) -> Self:
        _validate_parent_requirement(self.type, self.parent_geography_id)
        return self


class GeographyUpdate(SchemaModel):
    """PATCH payload for a geography."""

    code: str | None = None
    name: str | None = None
    alt_name: list[str] | None = None
    type: GeographyType | None = None
    code_standard: CodeStandard | None = None
    parent_geography_id: UUID | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_parent_requirement(self) -> Self:
        if {"type", "parent_geography_id"}.issubset(self.model_fields_set):
            _validate_parent_requirement(self.type, self.parent_geography_id)
        return self


class GeographyRead(TimestampedReadSchema, GeographyBase):
    """API read model for a geography."""


class GeographyMembershipBase(SchemaModel):
    """Shared geography-membership fields."""

    member_geography_id: UUID
    group_geography_id: UUID
    start_date: date | None = None
    end_date: date | None = None


class GeographyMembershipCreate(GeographyMembershipBase):
    """Payload for creating a geography membership."""


class GeographyMembershipUpdate(SchemaModel):
    """PATCH payload for a geography membership."""

    member_geography_id: UUID | None = None
    group_geography_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None


class GeographyMembershipRead(TimestampedReadSchema, GeographyMembershipBase):
    """API read model for a geography membership."""


class GeographyReadDetail(GeographyRead):
    """Read model including same-domain relationship rows."""

    member_memberships: list[GeographyMembershipRead] = Field(default_factory=list)
    group_memberships: list[GeographyMembershipRead] = Field(default_factory=list)


__all__ = [
    "GeographyBase",
    "GeographyCreate",
    "GeographyMembershipBase",
    "GeographyMembershipCreate",
    "GeographyMembershipRead",
    "GeographyMembershipUpdate",
    "GeographyRead",
    "GeographyReadDetail",
    "GeographyUpdate",
]
