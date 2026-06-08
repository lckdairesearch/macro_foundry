"""SQLAdmin views for tag-domain models."""

from macro_foundry.backend.admin._base import BaseModelView, relation_formatter
from macro_foundry.models import SeriesTag, Tag


class TagAdmin(BaseModelView, model=Tag):
    name = "Tag"
    name_plural = "Tags"
    column_list = [Tag.name, Tag.updated_at]
    column_searchable_list = [Tag.name]
    column_sortable_list = [Tag.name, Tag.updated_at]
    form_columns = [Tag.name]


class SeriesTagAdmin(BaseModelView, model=SeriesTag):
    name = "Series tag"
    name_plural = "Series tags"
    column_list = [SeriesTag.series, SeriesTag.tag]
    column_searchable_list = ["series.code", "series.name", "tag.name"]
    column_formatters = {
        SeriesTag.series: relation_formatter("series"),
        SeriesTag.tag: relation_formatter("tag"),
    }
    form_columns = [SeriesTag.series, SeriesTag.tag]


__all__ = ["SeriesTagAdmin", "TagAdmin"]
