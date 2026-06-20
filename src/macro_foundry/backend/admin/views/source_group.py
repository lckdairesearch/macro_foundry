"""SQLAdmin views for the provider-side source-group layer (ADR 0025 §4)."""

from macro_foundry.backend.admin._base import BaseModelView, relation_formatter
from macro_foundry.models import SourceGroup, SourceGroupMember


class SourceGroupAdmin(BaseModelView, model=SourceGroup):
    name = "Source group"
    name_plural = "Source groups"
    category = "Provider Layer"
    category_icon = "ti ti-building-bank"
    column_list = [
        SourceGroup.provider_catalog,
        SourceGroup.code,
        SourceGroup.name,
        SourceGroup.group_type,
        SourceGroup.parent_group,
        SourceGroup.updated_at,
    ]
    column_searchable_list = [SourceGroup.code, SourceGroup.name, "provider_catalog.name"]
    column_filters = [SourceGroup.group_type]
    column_sortable_list = [SourceGroup.name, SourceGroup.updated_at]
    column_default_sort = [(SourceGroup.name, False)]
    column_formatters = {
        SourceGroup.provider_catalog: relation_formatter("provider_catalog"),
        SourceGroup.parent_group: relation_formatter("parent_group"),
    }
    form_columns = [
        SourceGroup.provider_catalog,
        SourceGroup.parent_group,
        SourceGroup.group_type,
        SourceGroup.code,
        SourceGroup.name,
        SourceGroup.source_url,
        SourceGroup.notes,
    ]


class SourceGroupMemberAdmin(BaseModelView, model=SourceGroupMember):
    name = "Source group member"
    name_plural = "Source group members"
    category = "Provider Layer"
    category_icon = "ti ti-building-bank"
    column_list = [
        SourceGroupMember.source_group,
        SourceGroupMember.series_source,
        SourceGroupMember.row_label,
        SourceGroupMember.sort_order,
        SourceGroupMember.updated_at,
    ]
    column_searchable_list = [
        SourceGroupMember.row_label,
        "source_group.name",
        "series_source.external_code",
    ]
    column_sortable_list = [SourceGroupMember.sort_order, SourceGroupMember.updated_at]
    column_default_sort = [(SourceGroupMember.source_group_id, False), (SourceGroupMember.sort_order, False)]
    column_formatters = {
        SourceGroupMember.source_group: relation_formatter("source_group"),
        SourceGroupMember.series_source: relation_formatter("series_source"),
    }
    form_columns = [
        SourceGroupMember.source_group,
        SourceGroupMember.series_source,
        SourceGroupMember.row_label,
        SourceGroupMember.sort_order,
    ]


__all__ = ["SourceGroupAdmin", "SourceGroupMemberAdmin"]
