"""SQLAdmin views for ingestion models."""

from macro_foundry.backend.admin._base import BaseModelView, json_widget_args, relation_formatter
from macro_foundry.models import IngestionFeed


class IngestionFeedAdmin(BaseModelView, model=IngestionFeed):
    name = "Ingestion feed"
    name_plural = "Ingestion feeds"
    category = "Provider Layer"
    category_icon = "ti ti-building-bank"
    column_list = [
        IngestionFeed.series_source,
        IngestionFeed.feed_method,
        IngestionFeed.endpoint_url,
        IngestionFeed.cron_schedule,
        IngestionFeed.is_active,
        IngestionFeed.updated_at,
    ]
    column_searchable_list = [
        "series_source.external_code",
        "series_source.external_name",
        IngestionFeed.endpoint_url,
        IngestionFeed.file_path_pattern,
        IngestionFeed.cron_schedule,
    ]
    column_filters = [IngestionFeed.feed_method, IngestionFeed.is_active]
    column_sortable_list = [IngestionFeed.feed_method, IngestionFeed.updated_at]
    column_default_sort = [(IngestionFeed.updated_at, True)]
    column_formatters = {IngestionFeed.series_source: relation_formatter("series_source")}
    form_columns = [
        IngestionFeed.series_source,
        IngestionFeed.feed_method,
        IngestionFeed.endpoint_url,
        IngestionFeed.request_params,
        IngestionFeed.file_path_pattern,
        IngestionFeed.response_mapping,
        IngestionFeed.cron_schedule,
        IngestionFeed.is_active,
    ]
    form_widget_args = json_widget_args("request_params", "response_mapping")


__all__ = ["IngestionFeedAdmin"]
