"""SQLAdmin views for ingestion/computation run logs."""

from macro_foundry.backend.admin._base import BaseModelView, date_widget_args, datetime_widget_args, json_widget_args, relation_formatter
from macro_foundry.models import ComputationRunLog, IngestionRunLog, IngestionRunLogMember


class IngestionRunLogAdmin(BaseModelView, model=IngestionRunLog):
    name = "Ingestion run log"
    name_plural = "Ingestion run logs"
    category = "Observation Layer"
    category_icon = "ti ti-database"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [
        IngestionRunLog.ingestion_feed,
        IngestionRunLog.started_at,
        IngestionRunLog.finished_at,
        IngestionRunLog.status,
        IngestionRunLog.rows_fetched,
        IngestionRunLog.rows_inserted,
        IngestionRunLog.triggered_by,
        IngestionRunLog.created_at,
    ]
    column_searchable_list = [
        "ingestion_feed.endpoint_url",
        "ingestion_feed.file_path_pattern",
        IngestionRunLog.code_version,
        IngestionRunLog.error_message,
    ]
    column_filters = [IngestionRunLog.status, IngestionRunLog.triggered_by]
    column_sortable_list = [IngestionRunLog.started_at, IngestionRunLog.finished_at, IngestionRunLog.created_at]
    column_default_sort = [(IngestionRunLog.started_at, True)]
    column_formatters = {IngestionRunLog.ingestion_feed: relation_formatter("ingestion_feed")}
    form_columns = [
        IngestionRunLog.ingestion_feed,
        IngestionRunLog.started_at,
        IngestionRunLog.finished_at,
        IngestionRunLog.status,
        IngestionRunLog.rows_fetched,
        IngestionRunLog.rows_inserted,
        IngestionRunLog.rows_skipped,
        IngestionRunLog.error_message,
        IngestionRunLog.triggered_by,
        IngestionRunLog.code_version,
        IngestionRunLog.parameters,
        IngestionRunLog.notes,
    ]
    form_widget_args = {
        **json_widget_args("parameters"),
        **datetime_widget_args("started_at", "finished_at"),
    }


class ComputationRunLogAdmin(BaseModelView, model=ComputationRunLog):
    name = "Computation run log"
    name_plural = "Computation run logs"
    category = "Observation Layer"
    category_icon = "ti ti-database"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [
        ComputationRunLog.derived_series,
        ComputationRunLog.started_at,
        ComputationRunLog.finished_at,
        ComputationRunLog.status,
        ComputationRunLog.rows_computed,
        ComputationRunLog.rows_inserted,
        ComputationRunLog.triggered_by,
        ComputationRunLog.created_at,
    ]
    column_searchable_list = [
        "derived_series.description",
        ComputationRunLog.code_version,
        ComputationRunLog.error_message,
    ]
    column_filters = [
        ComputationRunLog.status,
        ComputationRunLog.triggered_by,
        ComputationRunLog.input_vintage_policy,
        ComputationRunLog.output_mode,
    ]
    column_sortable_list = [ComputationRunLog.started_at, ComputationRunLog.finished_at, ComputationRunLog.created_at]
    column_default_sort = [(ComputationRunLog.started_at, True)]
    column_formatters = {ComputationRunLog.derived_series: relation_formatter("derived_series")}
    form_columns = [
        ComputationRunLog.derived_series,
        ComputationRunLog.started_at,
        ComputationRunLog.finished_at,
        ComputationRunLog.status,
        ComputationRunLog.rows_computed,
        ComputationRunLog.rows_inserted,
        ComputationRunLog.rows_updated,
        ComputationRunLog.rows_skipped,
        ComputationRunLog.error_message,
        ComputationRunLog.triggered_by,
        ComputationRunLog.code_version,
        ComputationRunLog.input_vintage_policy,
        ComputationRunLog.input_vintage_date,
        ComputationRunLog.parameters,
        ComputationRunLog.output_mode,
        ComputationRunLog.notes,
    ]
    form_widget_args = {
        **json_widget_args("parameters"),
        **date_widget_args("input_vintage_date"),
        **datetime_widget_args("started_at", "finished_at"),
    }


class IngestionRunLogMemberAdmin(BaseModelView, model=IngestionRunLogMember):
    name = "Ingestion run log member"
    name_plural = "Ingestion run log members"
    category = "Observation Layer"
    category_icon = "ti ti-database"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [
        IngestionRunLogMember.ingestion_run_log,
        IngestionRunLogMember.ingestion_feed_member,
        IngestionRunLogMember.status,
        IngestionRunLogMember.rows_fetched,
        IngestionRunLogMember.rows_inserted,
        IngestionRunLogMember.rows_skipped,
        IngestionRunLogMember.created_at,
    ]
    column_searchable_list = [
        IngestionRunLogMember.error_message,
        "ingestion_feed_member.selector_type",
    ]
    column_filters = [IngestionRunLogMember.status]
    column_sortable_list = [IngestionRunLogMember.created_at]
    column_default_sort = [(IngestionRunLogMember.created_at, True)]
    column_formatters = {
        IngestionRunLogMember.ingestion_run_log: relation_formatter("ingestion_run_log"),
        IngestionRunLogMember.ingestion_feed_member: relation_formatter("ingestion_feed_member"),
    }
    form_columns = [
        IngestionRunLogMember.ingestion_run_log,
        IngestionRunLogMember.ingestion_feed_member,
        IngestionRunLogMember.status,
        IngestionRunLogMember.rows_fetched,
        IngestionRunLogMember.rows_inserted,
        IngestionRunLogMember.rows_skipped,
        IngestionRunLogMember.error_message,
        IngestionRunLogMember.diagnostics,
        IngestionRunLogMember.notes,
    ]
    form_widget_args = json_widget_args("diagnostics")


__all__ = ["ComputationRunLogAdmin", "IngestionRunLogAdmin", "IngestionRunLogMemberAdmin"]
