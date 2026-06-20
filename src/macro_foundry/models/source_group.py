"""Provider source-group SQLAlchemy models (ADR 0025 §4)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from macro_foundry.db.base import TimestampedBase
from macro_foundry.enums import SourceGroupType
from macro_foundry.models._schema_policy import enum_column, fk_uuid

if TYPE_CHECKING:
    from macro_foundry.models.provider import ProviderCatalog, SeriesSource


class SourceGroup(TimestampedBase):
    """A provider-side publication unit (release, table, dataset, dashboard).

    Typed and self-nesting (a release contains tables). Owned by a
    `provider_catalog`. Distinct from the canonical `series_hierarchy_edges`
    decomposition and from the runtime `ingestion_feed` fetch unit.
    """

    __tablename__ = "source_groups"
    __table_args__ = (
        UniqueConstraint(
            "provider_catalog_id",
            "code",
            name="uq_source_groups_provider_catalog_id_code",
        ),
        CheckConstraint(
            "parent_group_id != id",
            name="ck_source_groups_no_self_parent",
        ),
    )

    provider_catalog_id: Mapped[uuid.UUID] = fk_uuid(
        "provider_catalogs.id",
        ondelete="RESTRICT",
        nullable=False,
    )
    parent_group_id: Mapped[uuid.UUID | None] = fk_uuid(
        "source_groups.id",
        ondelete="RESTRICT",
        nullable=True,
    )
    group_type: Mapped[SourceGroupType] = enum_column(
        "source_groups",
        "group_type",
        SourceGroupType,
        nullable=False,
    )
    code: Mapped[str | None] = mapped_column(String(), nullable=True)
    name: Mapped[str] = mapped_column(String(), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(), nullable=True)

    provider_catalog: Mapped["ProviderCatalog"] = relationship(
        "ProviderCatalog",
        lazy="selectin",
    )
    parent_group: Mapped["SourceGroup | None"] = relationship(
        "SourceGroup",
        back_populates="child_groups",
        foreign_keys=lambda: [SourceGroup.parent_group_id],
        remote_side=lambda: [SourceGroup.id],
        lazy="selectin",
    )
    child_groups: Mapped[list["SourceGroup"]] = relationship(
        "SourceGroup",
        back_populates="parent_group",
        foreign_keys=lambda: [SourceGroup.parent_group_id],
        lazy="selectin",
        passive_deletes=True,
    )
    members: Mapped[list["SourceGroupMember"]] = relationship(
        "SourceGroupMember",
        back_populates="source_group",
        lazy="selectin",
        passive_deletes=True,
    )


class SourceGroupMember(TimestampedBase):
    """Membership of a provider representation (`series_source`) in a source group.

    M:N, so a `series_source` is not fixed to one group (it can sit in a release,
    a table, and a dashboard at once).
    """

    __tablename__ = "source_group_members"
    __table_args__ = (
        UniqueConstraint(
            "source_group_id",
            "series_source_id",
            name="uq_source_group_members_source_group_id_series_source_id",
        ),
    )

    source_group_id: Mapped[uuid.UUID] = fk_uuid(
        "source_groups.id",
        ondelete="CASCADE",
        nullable=False,
    )
    series_source_id: Mapped[uuid.UUID] = fk_uuid(
        "series_sources.id",
        ondelete="CASCADE",
        nullable=False,
    )
    row_label: Mapped[str | None] = mapped_column(String(), nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    source_group: Mapped["SourceGroup"] = relationship(
        "SourceGroup",
        back_populates="members",
        lazy="selectin",
    )
    series_source: Mapped["SeriesSource"] = relationship(
        "SeriesSource",
        lazy="selectin",
    )


__all__ = ["SourceGroup", "SourceGroupMember"]
