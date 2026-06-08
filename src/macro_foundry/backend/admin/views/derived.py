"""SQLAdmin views for derived-series models."""

from macro_foundry.backend.admin._base import BaseModelView, json_widget_args, relation_formatter
from macro_foundry.models import DerivationInput, DerivedSeries


class DerivedSeriesAdmin(BaseModelView, model=DerivedSeries):
    name = "Derived series"
    name_plural = "Derived series"
    category = "Series Catalog"
    category_icon = "ti ti-chart-line"
    column_list = [
        DerivedSeries.series,
        DerivedSeries.execution_policy,
        DerivedSeries.is_deterministic,
        DerivedSeries.requires_vintage_awareness,
        DerivedSeries.updated_at,
    ]
    column_searchable_list = ["series.code", "series.name", DerivedSeries.description, DerivedSeries.code_ref]
    column_filters = [
        DerivedSeries.execution_policy,
        DerivedSeries.is_deterministic,
        DerivedSeries.requires_vintage_awareness,
    ]
    column_sortable_list = [DerivedSeries.updated_at]
    column_default_sort = [(DerivedSeries.updated_at, True)]
    column_formatters = {DerivedSeries.series: relation_formatter("series")}
    form_columns = [
        DerivedSeries.series,
        DerivedSeries.formula_config,
        DerivedSeries.description,
        DerivedSeries.execution_policy,
        DerivedSeries.is_deterministic,
        DerivedSeries.requires_vintage_awareness,
        DerivedSeries.code_ref,
    ]
    form_widget_args = json_widget_args("formula_config")


class DerivationInputAdmin(BaseModelView, model=DerivationInput):
    name = "Derivation input"
    name_plural = "Derivation inputs"
    category = "Series Catalog"
    category_icon = "ti ti-chart-line"
    column_list = [
        DerivationInput.derived_series,
        DerivationInput.input_series,
        DerivationInput.notes,
        DerivationInput.updated_at,
    ]
    column_searchable_list = [
        "derived_series.description",
        "input_series.code",
        "input_series.name",
        DerivationInput.notes,
    ]
    column_sortable_list = [DerivationInput.updated_at]
    column_default_sort = [(DerivationInput.updated_at, True)]
    column_formatters = {
        DerivationInput.derived_series: relation_formatter("derived_series"),
        DerivationInput.input_series: relation_formatter("input_series"),
    }
    form_columns = [
        DerivationInput.derived_series,
        DerivationInput.input_series,
        DerivationInput.notes,
    ]


__all__ = ["DerivationInputAdmin", "DerivedSeriesAdmin"]
