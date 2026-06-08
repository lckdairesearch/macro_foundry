"""SQLAdmin views for geography-domain models."""

from macro_foundry.backend.admin._base import BaseModelView, relation_formatter
from macro_foundry.models import Geography, GeographyMembership


class GeographyAdmin(BaseModelView, model=Geography):
    name = "Geography"
    name_plural = "Geographies"
    category = "Core Curation"
    category_icon = "ti ti-world"
    column_list = [
        Geography.code,
        Geography.name,
        Geography.type,
        Geography.code_standard,
        Geography.parent_geography,
        Geography.updated_at,
    ]
    column_searchable_list = [Geography.code, Geography.name, "parent_geography.code", "parent_geography.name"]
    column_filters = [Geography.type, Geography.code_standard]
    column_sortable_list = [Geography.code, Geography.name, Geography.updated_at]
    column_default_sort = [(Geography.code, False)]
    column_formatters = {Geography.parent_geography: relation_formatter("parent_geography")}
    form_columns = [
        Geography.code,
        Geography.name,
        Geography.alt_name,
        Geography.type,
        Geography.code_standard,
        Geography.parent_geography,
        Geography.notes,
    ]


class GeographyMembershipAdmin(BaseModelView, model=GeographyMembership):
    name = "Geography membership"
    name_plural = "Geography memberships"
    category = "Core Curation"
    category_icon = "ti ti-world"
    column_list = [
        GeographyMembership.member_geography,
        GeographyMembership.group_geography,
        GeographyMembership.start_date,
        GeographyMembership.end_date,
        GeographyMembership.updated_at,
    ]
    column_searchable_list = [
        "member_geography.code",
        "member_geography.name",
        "group_geography.code",
        "group_geography.name",
    ]
    column_sortable_list = [
        GeographyMembership.start_date,
        GeographyMembership.end_date,
        GeographyMembership.updated_at,
    ]
    column_default_sort = [(GeographyMembership.updated_at, True)]
    column_formatters = {
        GeographyMembership.member_geography: relation_formatter("member_geography"),
        GeographyMembership.group_geography: relation_formatter("group_geography"),
    }
    form_columns = [
        GeographyMembership.member_geography,
        GeographyMembership.group_geography,
        GeographyMembership.start_date,
        GeographyMembership.end_date,
    ]


__all__ = ["GeographyAdmin", "GeographyMembershipAdmin"]
