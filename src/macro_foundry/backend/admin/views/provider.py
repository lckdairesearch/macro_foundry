"""SQLAdmin views for provider-domain models."""

from macro_foundry.backend.admin._base import BaseModelView, json_widget_args, relation_formatter
from macro_foundry.models import Provider, ProviderCatalog, SeriesSource


class ProviderAdmin(BaseModelView, model=Provider):
    name = "Provider"
    name_plural = "Providers"
    category = "Provider Layer"
    category_icon = "ti ti-building-bank"
    column_list = [Provider.name, Provider.type, Provider.homepage_url, Provider.is_active, Provider.updated_at]
    column_searchable_list = [Provider.name, Provider.homepage_url, Provider.doc_url]
    column_filters = [Provider.type, Provider.is_active]
    column_sortable_list = [Provider.name, Provider.updated_at]
    column_default_sort = [(Provider.name, False)]
    form_columns = [
        Provider.name,
        Provider.alt_name,
        Provider.type,
        Provider.homepage_url,
        Provider.doc_url,
        Provider.base_url,
        Provider.credentials_ref,
        Provider.notes,
        Provider.is_active,
    ]


class ProviderCatalogAdmin(BaseModelView, model=ProviderCatalog):
    name = "Provider catalog"
    name_plural = "Provider catalogs"
    category = "Provider Layer"
    category_icon = "ti ti-building-bank"
    column_list = [
        ProviderCatalog.provider,
        ProviderCatalog.name,
        ProviderCatalog.catalog_url,
        ProviderCatalog.is_placeholder,
        ProviderCatalog.updated_at,
    ]
    column_searchable_list = [ProviderCatalog.name, "provider.name"]
    column_filters = [ProviderCatalog.is_placeholder]
    column_sortable_list = [ProviderCatalog.name, ProviderCatalog.updated_at]
    column_default_sort = [(ProviderCatalog.name, False)]
    column_formatters = {ProviderCatalog.provider: relation_formatter("provider")}
    form_columns = [
        ProviderCatalog.provider,
        ProviderCatalog.name,
        ProviderCatalog.catalog_url,
        ProviderCatalog.doc_url,
        ProviderCatalog.notes,
        ProviderCatalog.is_placeholder,
    ]


class SeriesSourceAdmin(BaseModelView, model=SeriesSource):
    name = "Series source"
    name_plural = "Series sources"
    category = "Provider Layer"
    category_icon = "ti ti-building-bank"
    column_list = [
        SeriesSource.series,
        SeriesSource.provider_catalog,
        SeriesSource.external_code,
        SeriesSource.provider_role,
        SeriesSource.priority,
        SeriesSource.updated_at,
    ]
    column_searchable_list = [
        SeriesSource.external_code,
        SeriesSource.external_name,
        "series.code",
        "series.name",
        "provider_catalog.name",
    ]
    column_filters = [SeriesSource.provider_role, SeriesSource.priority]
    column_sortable_list = [SeriesSource.external_code, SeriesSource.priority, SeriesSource.updated_at]
    column_default_sort = [(SeriesSource.priority, False), (SeriesSource.external_code, False)]
    column_formatters = {
        SeriesSource.series: relation_formatter("series"),
        SeriesSource.provider_catalog: relation_formatter("provider_catalog"),
    }
    form_columns = [
        SeriesSource.series,
        SeriesSource.provider_catalog,
        SeriesSource.external_code,
        SeriesSource.external_name,
        SeriesSource.priority,
        SeriesSource.provider_role,
        SeriesSource.value_transform,
        SeriesSource.start_date,
        SeriesSource.end_date,
    ]
    form_widget_args = json_widget_args("value_transform")


__all__ = ["ProviderAdmin", "ProviderCatalogAdmin", "SeriesSourceAdmin"]
