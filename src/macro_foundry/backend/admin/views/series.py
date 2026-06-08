"""SQLAdmin views for series-domain models."""

from macro_foundry.backend.admin._base import BaseModelView, relation_formatter
from macro_foundry.models import Series, SeriesFamily, SeriesFamilyMember


class SeriesAdmin(BaseModelView, model=Series):
    name = "Series"
    name_plural = "Series"
    column_list = [
        Series.code,
        Series.name,
        Series.geography,
        Series.frequency,
        Series.measure,
        Series.seasonal_adjustment,
        Series.is_active,
        Series.updated_at,
    ]
    column_searchable_list = [Series.code, Series.name, "geography.code", "geography.name"]
    column_filters = [Series.origin_type, Series.frequency, Series.measure, Series.is_active]
    column_sortable_list = [Series.code, Series.name, Series.updated_at]
    column_formatters = {
        Series.geography: relation_formatter("geography"),
        Series.replaced_by_series: relation_formatter("replaced_by_series"),
    }
    form_columns = [
        Series.code,
        Series.name,
        Series.description,
        Series.origin_type,
        Series.geography,
        Series.frequency,
        Series.temporal_stock_flow,
        Series.unit_kind,
        Series.unit_scale,
        Series.unit_label,
        Series.price_basis,
        Series.currency_code,
        Series.measure,
        Series.measure_horizon,
        Series.annualized,
        Series.seasonal_adjustment,
        Series.reference_kind,
        Series.reference_year,
        Series.reference_label,
        Series.replaced_by_series,
        Series.start_date,
        Series.end_date,
        Series.is_active,
    ]


class SeriesFamilyAdmin(BaseModelView, model=SeriesFamily):
    name = "Series family"
    name_plural = "Series families"
    column_list = [
        SeriesFamily.code,
        SeriesFamily.name,
        SeriesFamily.concept,
        SeriesFamily.geography,
        SeriesFamily.updated_at,
    ]
    column_searchable_list = [SeriesFamily.code, SeriesFamily.name, "concept.code", "concept.name", "geography.code"]
    column_sortable_list = [SeriesFamily.code, SeriesFamily.name, SeriesFamily.updated_at]
    column_formatters = {
        SeriesFamily.concept: relation_formatter("concept"),
        SeriesFamily.geography: relation_formatter("geography"),
    }
    form_columns = [
        SeriesFamily.code,
        SeriesFamily.name,
        SeriesFamily.description,
        SeriesFamily.concept,
        SeriesFamily.geography,
    ]


class SeriesFamilyMemberAdmin(BaseModelView, model=SeriesFamilyMember):
    name = "Series family member"
    name_plural = "Series family members"
    column_list = [
        SeriesFamilyMember.family,
        SeriesFamilyMember.series,
        SeriesFamilyMember.variant,
        SeriesFamilyMember.is_primary,
        SeriesFamilyMember.updated_at,
    ]
    column_searchable_list = ["family.code", "family.name", "series.code", "series.name", SeriesFamilyMember.variant]
    column_filters = [SeriesFamilyMember.is_primary]
    column_sortable_list = [SeriesFamilyMember.variant, SeriesFamilyMember.updated_at]
    column_formatters = {
        SeriesFamilyMember.family: relation_formatter("family"),
        SeriesFamilyMember.series: relation_formatter("series"),
    }
    form_columns = [
        SeriesFamilyMember.family,
        SeriesFamilyMember.series,
        SeriesFamilyMember.variant,
        SeriesFamilyMember.is_primary,
    ]


__all__ = ["SeriesAdmin", "SeriesFamilyAdmin", "SeriesFamilyMemberAdmin"]
