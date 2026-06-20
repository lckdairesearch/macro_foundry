"""SQLAdmin views for the V8 category tree (ADR 0025 §1, §2)."""

from macro_foundry.backend.admin._base import BaseModelView, relation_formatter
from macro_foundry.models import Category, CategoryEdge


class CategoryAdmin(BaseModelView, model=Category):
    name = "Category"
    name_plural = "Categories"
    category = "Category Tree"
    category_icon = "ti ti-sitemap"
    column_list = [
        Category.code,
        Category.name,
        Category.kind,
        Category.description,
        Category.updated_at,
    ]
    column_searchable_list = [Category.code, Category.name]
    column_filters = [Category.kind]
    column_sortable_list = [Category.code, Category.name, Category.updated_at]
    column_default_sort = [(Category.code, False)]
    # The embedding vector and its versioning columns are internal (ADR 0025 §1);
    # never render the 1536-dim vector in the detail view.
    column_details_exclude_list = [
        Category.embedding,
        Category.embedding_model,
        Category.embedding_input_hash,
    ]
    form_columns = [
        Category.code,
        Category.name,
        Category.description,
        Category.kind,
    ]


class CategoryEdgeAdmin(BaseModelView, model=CategoryEdge):
    name = "Category edge"
    name_plural = "Category edges"
    category = "Category Tree"
    category_icon = "ti ti-sitemap"
    column_list = [
        CategoryEdge.parent_category,
        CategoryEdge.child_category,
        CategoryEdge.sort_order,
        CategoryEdge.updated_at,
    ]
    column_searchable_list = [
        "parent_category.code",
        "parent_category.name",
        "child_category.code",
        "child_category.name",
    ]
    column_sortable_list = [CategoryEdge.sort_order, CategoryEdge.updated_at]
    column_default_sort = [(CategoryEdge.parent_category_id, False), (CategoryEdge.sort_order, False)]
    column_formatters = {
        CategoryEdge.parent_category: relation_formatter("parent_category"),
        CategoryEdge.child_category: relation_formatter("child_category"),
    }
    form_columns = [
        CategoryEdge.parent_category,
        CategoryEdge.child_category,
        CategoryEdge.sort_order,
    ]


__all__ = ["CategoryAdmin", "CategoryEdgeAdmin"]
