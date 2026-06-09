"""SQLAdmin views for ingestion models."""

from macro_foundry.backend.admin._base import BaseModelView, json_widget_args, relation_formatter
from macro_foundry.models import IngestionFeed, IngestionFeedMember


class IngestionFeedAdmin(BaseModelView, model=IngestionFeed):
    name = "Ingestion feed"
    name_plural = "Ingestion feeds"
    category = "Provider Layer"
    category_icon = "ti ti-building-bank"
    column_list = [
        IngestionFeed.feed_method,
        IngestionFeed.endpoint_url,
        IngestionFeed.file_path_pattern,
        IngestionFeed.cron_schedule,
        IngestionFeed.is_active,
        IngestionFeed.updated_at,
    ]
    column_searchable_list = [
        IngestionFeed.endpoint_url,
        IngestionFeed.file_path_pattern,
        IngestionFeed.cron_schedule,
    ]
    column_filters = [IngestionFeed.feed_method, IngestionFeed.is_active]
    column_sortable_list = [IngestionFeed.feed_method, IngestionFeed.updated_at]
    column_default_sort = [(IngestionFeed.updated_at, True)]
    form_columns = [
        IngestionFeed.feed_method,
        IngestionFeed.endpoint_url,
        IngestionFeed.request_params,
        IngestionFeed.file_path_pattern,
        IngestionFeed.response_mapping,
        IngestionFeed.cron_schedule,
        IngestionFeed.is_active,
    ]
    form_widget_args = json_widget_args("request_params", "response_mapping")


class IngestionFeedMemberAdmin(BaseModelView, model=IngestionFeedMember):
    name = "Ingestion feed member"
    name_plural = "Ingestion feed members"
    category = "Provider Layer"
    category_icon = "ti ti-building-bank"
    column_list = [
        IngestionFeedMember.ingestion_feed,
        IngestionFeedMember.series_source,
        IngestionFeedMember.selector_type,
        IngestionFeedMember.execution_order,
        IngestionFeedMember.is_active,
        IngestionFeedMember.updated_at,
    ]
    column_searchable_list = [
        IngestionFeedMember.selector_type,
        "series_source.external_code",
        "series_source.external_name",
    ]
    column_filters = [IngestionFeedMember.selector_type, IngestionFeedMember.is_active]
    column_sortable_list = [
        IngestionFeedMember.selector_type,
        IngestionFeedMember.execution_order,
        IngestionFeedMember.updated_at,
    ]
    column_default_sort = [(IngestionFeedMember.execution_order, False)]
    column_formatters = {
        IngestionFeedMember.ingestion_feed: relation_formatter("ingestion_feed"),
        IngestionFeedMember.series_source: relation_formatter("series_source"),
    }
    form_columns = [
        IngestionFeedMember.ingestion_feed,
        IngestionFeedMember.series_source,
        IngestionFeedMember.selector_type,
        IngestionFeedMember.selector_config,
        IngestionFeedMember.execution_order,
        IngestionFeedMember.is_active,
    ]
    form_widget_args = json_widget_args("selector_config")


__all__ = ["IngestionFeedAdmin", "IngestionFeedMemberAdmin"]
