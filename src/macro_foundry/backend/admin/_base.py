"""Shared SQLAdmin base helpers and project defaults."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from enum import Enum
from typing import Any

import anyio
from sqlalchemy import Boolean
from sqlalchemy import select
from sqlalchemy.sql.sqltypes import Enum as SAEnum
from sqladmin.filters import BooleanFilter, OperationColumnFilter, StaticValuesFilter
from sqladmin import ModelView
from sqladmin.forms import ModelConverter
from sqladmin.helpers import is_async_session_maker


def _enum_label(value: Enum | Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def describe_instance(obj: Any) -> str:
    """Render a concise label for related objects in lists and forms."""

    if obj is None:
        return ""

    code = getattr(obj, "code", None)
    name = getattr(obj, "name", None)
    if code and name:
        return f"{code} - {name}"
    if code:
        return str(code)
    if name:
        return str(name)

    title = getattr(obj, "title", None)
    if title:
        return str(title)

    external_code = getattr(obj, "external_code", None)
    external_name = getattr(obj, "external_name", None)
    if external_code and external_name:
        return f"{external_code} - {external_name}"
    if external_code:
        return str(external_code)

    description = getattr(obj, "description", None)
    if description:
        return str(description)

    feed_method = getattr(obj, "feed_method", None)
    if feed_method is not None:
        target = (
            getattr(obj, "endpoint_url", None)
            or getattr(obj, "file_path_pattern", None)
            or getattr(obj, "cron_schedule", None)
        )
        if target:
            return f"{_enum_label(feed_method)} - {target}"
        return _enum_label(feed_method)

    status = getattr(obj, "status", None)
    started_at = getattr(obj, "started_at", None)
    if status is not None and started_at is not None:
        timestamp = started_at.isoformat(sep=" ", timespec="minutes")
        return f"{_enum_label(status)} - {timestamp}"
    if status is not None:
        return _enum_label(status)

    for attr_name in ("target_ref", "code_ref", "homepage_url", "doc_url"):
        value = getattr(obj, attr_name, None)
        if value:
            return str(value)

    obj_id = getattr(obj, "id", None)
    if obj_id is not None:
        return str(obj_id)

    return str(obj)


class AdminModelConverter(ModelConverter):
    """Render foreign-key select choices with project labels instead of reprs."""

    async def _prepare_select_options(
        self,
        prop: Any,
        session_maker: Any,
    ) -> list[tuple[str, str]]:
        target_model = prop.mapper.class_
        stmt = select(target_model)

        if is_async_session_maker(session_maker):
            async with session_maker() as session:
                objects = await session.execute(stmt)
                return [
                    (str(self._get_identifier_value(obj)), describe_instance(obj))
                    for obj in objects.scalars().unique().all()
                ]

        with session_maker() as session:
            objects = await anyio.to_thread.run_sync(session.execute, stmt)
            return [
                (str(self._get_identifier_value(obj)), describe_instance(obj))
                for obj in objects.scalars().unique().all()
            ]


def relation_formatter(attr_name: str) -> Callable[[Any, str], str]:
    """Build a list-view formatter for a direct relationship attribute."""

    def _formatter(model: Any, _attribute: str) -> str:
        return describe_instance(getattr(model, attr_name, None))

    return _formatter


def json_widget_args(*field_names: str) -> dict[str, dict[str, Any]]:
    """Apply a larger monospace textarea to JSONB-backed fields."""

    return {
        field_name: {
            "rows": 8,
            "style": "font-family: monospace;",
        }
        for field_name in field_names
    }


def date_widget_args(*field_names: str) -> dict[str, dict[str, Any]]:
    """Provide placeholders for date-heavy admin forms."""

    return {
        field_name: {
            "placeholder": date.today().isoformat(),
        }
        for field_name in field_names
    }


def datetime_widget_args(*field_names: str) -> dict[str, dict[str, Any]]:
    """Provide placeholders for datetime-heavy admin forms."""

    return {
        field_name: {
            "placeholder": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        for field_name in field_names
    }


class BaseModelView(ModelView):
    """Project-level SQLAdmin defaults shared by all concrete views."""

    can_view_details = False
    page_size = 25
    page_size_options = [25, 50, 100]
    use_pretty_export = True
    form_excluded_columns = ["id", "created_at", "updated_at"]
    form_converter = AdminModelConverter

    def _build_filter(self, filter_: Any) -> Any:
        if hasattr(filter_, "parameter_name"):
            return filter_

        column = getattr(self.model, filter_) if isinstance(filter_, str) else filter_
        column_type = column.property.columns[0].type

        if isinstance(column_type, Boolean):
            return BooleanFilter(column)

        if isinstance(column_type, SAEnum) and column_type.enum_class is not None:
            values = [
                (str(member.value), str(member.value))
                for member in column_type.enum_class
            ]
            return StaticValuesFilter(column, values=values)

        return OperationColumnFilter(column)

    def get_filters(self) -> list[Any]:
        filters = getattr(self, "_normalized_column_filters", None)
        if filters is not None:
            return filters

        raw_filters = getattr(self, "column_filters", None) or []
        filters = [self._build_filter(filter_) for filter_ in raw_filters]
        self._normalized_column_filters = filters
        return filters


__all__ = [
    "BaseModelView",
    "date_widget_args",
    "datetime_widget_args",
    "describe_instance",
    "json_widget_args",
    "relation_formatter",
]
