"""SQLAdmin views for series-domain models."""

from macro_foundry.backend.admin._base import BaseModelView, relation_formatter
from macro_foundry.models import Series, Indicator, IndicatorVariant, SeriesHierarchyEdge


class SeriesAdmin(BaseModelView, model=Series):
    name = "Series"
    name_plural = "Series"
    category = "Series Catalog"
    category_icon = "ti ti-chart-line"
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
    column_default_sort = [(Series.code, False)]
    column_formatters = {
        Series.geography: relation_formatter("geography"),
        Series.replaced_by_series: relation_formatter("replaced_by_series"),
    }
    form_columns = [
        Series.code,
        Series.name,
        Series.alt_name,
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


class IndicatorAdmin(BaseModelView, model=Indicator):
    name = "Indicator"
    name_plural = "Indicators"
    category = "Series Catalog"
    category_icon = "ti ti-chart-line"
    column_list = [
        Indicator.code,
        Indicator.name,
        Indicator.concept,
        Indicator.geography,
        Indicator.updated_at,
    ]
    column_searchable_list = [Indicator.code, Indicator.name, "concept.code", "concept.name", "geography.code"]
    column_sortable_list = [Indicator.code, Indicator.name, Indicator.updated_at]
    column_default_sort = [(Indicator.code, False)]
    column_formatters = {
        Indicator.concept: relation_formatter("concept"),
        Indicator.geography: relation_formatter("geography"),
    }
    form_columns = [
        Indicator.code,
        Indicator.name,
        Indicator.description,
        Indicator.concept,
        Indicator.geography,
    ]


class IndicatorVariantAdmin(BaseModelView, model=IndicatorVariant):
    name = "Indicator variant"
    name_plural = "Indicator variants"
    category = "Series Catalog"
    category_icon = "ti ti-chart-line"
    column_list = [
        IndicatorVariant.indicator,
        IndicatorVariant.series,
        IndicatorVariant.label,
        IndicatorVariant.is_default,
        IndicatorVariant.updated_at,
    ]
    column_searchable_list = ["indicator.code", "indicator.name", "series.code", "series.name", IndicatorVariant.label]
    column_filters = [IndicatorVariant.is_default]
    column_sortable_list = [IndicatorVariant.label, IndicatorVariant.updated_at]
    column_default_sort = [(IndicatorVariant.updated_at, True)]
    column_formatters = {
        IndicatorVariant.indicator: relation_formatter("indicator"),
        IndicatorVariant.series: relation_formatter("series"),
    }
    form_columns = [
        IndicatorVariant.indicator,
        IndicatorVariant.series,
        IndicatorVariant.label,
        IndicatorVariant.is_default,
    ]


class SeriesHierarchyEdgeAdmin(BaseModelView, model=SeriesHierarchyEdge):
    name = "Series hierarchy edge"
    name_plural = "Series hierarchy edges"
    category = "Series Catalog"
    category_icon = "ti ti-chart-line"
    column_list = [
        SeriesHierarchyEdge.parent_series,
        SeriesHierarchyEdge.child_series,
        SeriesHierarchyEdge.sort_order,
        SeriesHierarchyEdge.updated_at,
    ]
    column_searchable_list = ["parent_series.code", "parent_series.name", "child_series.code", "child_series.name"]
    column_sortable_list = [SeriesHierarchyEdge.sort_order, SeriesHierarchyEdge.updated_at]
    column_default_sort = [(SeriesHierarchyEdge.parent_series_id, False), (SeriesHierarchyEdge.sort_order, False)]
    column_formatters = {
        SeriesHierarchyEdge.parent_series: relation_formatter("parent_series"),
        SeriesHierarchyEdge.child_series: relation_formatter("child_series"),
    }
    form_columns = [
        SeriesHierarchyEdge.parent_series,
        SeriesHierarchyEdge.child_series,
        SeriesHierarchyEdge.sort_order,
        SeriesHierarchyEdge.notes,
    ]


__all__ = ["SeriesAdmin", "IndicatorAdmin", "IndicatorVariantAdmin", "SeriesHierarchyEdgeAdmin"]
