"""SQLAdmin views for series-domain models."""

from macro_foundry.backend.admin._base import BaseModelView, relation_formatter
from macro_foundry.models import Series, SeriesHierarchyEdge


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


__all__ = ["SeriesAdmin", "SeriesHierarchyEdgeAdmin"]
