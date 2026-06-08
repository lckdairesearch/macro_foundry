"""SQLAdmin views for observation-domain models."""

from macro_foundry.backend.admin._base import BaseModelView, relation_formatter
from macro_foundry.models import Observation


class ObservationAdmin(BaseModelView, model=Observation):
    name = "Observation"
    name_plural = "Observations"
    can_create = False
    can_edit = False
    can_delete = False
    column_list = [
        Observation.series,
        Observation.period_start,
        Observation.period_end,
        Observation.vintage_date,
        Observation.value,
        Observation.ingestion_run_log,
        Observation.computation_run_log,
        Observation.created_at,
    ]
    column_searchable_list = ["series.code", "series.name"]
    column_filters = [Observation.period_start, Observation.vintage_date]
    column_sortable_list = [Observation.period_start, Observation.vintage_date, Observation.created_at]
    column_formatters = {
        Observation.series: relation_formatter("series"),
        Observation.ingestion_run_log: relation_formatter("ingestion_run_log"),
        Observation.computation_run_log: relation_formatter("computation_run_log"),
    }


__all__ = ["ObservationAdmin"]
