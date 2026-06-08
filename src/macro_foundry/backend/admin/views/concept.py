"""SQLAdmin views for concept-domain models."""

from macro_foundry.backend.admin._base import BaseModelView
from macro_foundry.models import Concept


class ConceptAdmin(BaseModelView, model=Concept):
    name = "Concept"
    name_plural = "Concepts"
    column_list = [Concept.code, Concept.name, Concept.description, Concept.updated_at]
    column_searchable_list = [Concept.code, Concept.name, Concept.description]
    column_sortable_list = [Concept.code, Concept.name, Concept.updated_at]
    form_columns = [Concept.code, Concept.name, Concept.description]


__all__ = ["ConceptAdmin"]
