"""SQLAdmin views for tag-domain models."""

from macro_foundry.backend.admin._base import BaseModelView, relation_formatter
from macro_foundry.models import ConceptTag, Tag


class TagAdmin(BaseModelView, model=Tag):
    name = "Tag"
    name_plural = "Tags"
    category = "Core Curation"
    category_icon = "ti ti-tags"
    column_list = [Tag.code, Tag.name, Tag.updated_at]
    column_searchable_list = [Tag.code, Tag.name]
    column_sortable_list = [Tag.code, Tag.name, Tag.updated_at]
    column_default_sort = [(Tag.code, False)]
    form_columns = [Tag.code, Tag.name]


class ConceptTagAdmin(BaseModelView, model=ConceptTag):
    name = "Concept tag"
    name_plural = "Concept tags"
    category = "Core Curation"
    category_icon = "ti ti-tags"
    column_list = [ConceptTag.concept, ConceptTag.tag]
    column_searchable_list = ["concept.code", "concept.name", "tag.name"]
    column_formatters = {
        ConceptTag.concept: relation_formatter("concept"),
        ConceptTag.tag: relation_formatter("tag"),
    }
    form_columns = [ConceptTag.concept, ConceptTag.tag]


__all__ = ["ConceptTagAdmin", "TagAdmin"]
