"""Thin in-repo CRUD router generator for simple tables."""

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect

from macro_foundry.backend.deps import get_session, verify_token

_RESERVED_QUERY_PARAMS = {"limit", "offset"}


@dataclass(frozen=True)
class _ColumnSpec:
    """Column metadata used for path-key and query-filter coercion."""

    name: str
    python_type: Any


def _infer_python_type(column: Any) -> Any:
    enum_class = getattr(column.type, "enum_class", None)
    if enum_class is not None:
        return enum_class
    try:
        return column.type.python_type
    except NotImplementedError:
        return object


def _build_column_specs(columns: list[Any]) -> list[_ColumnSpec]:
    return [_ColumnSpec(name=column.key, python_type=_infer_python_type(column)) for column in columns]


def _coerce_value(raw_value: str, python_type: Any, *, location: str) -> Any:
    try:
        return TypeAdapter(python_type).validate_python(raw_value)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    **error,
                    "loc": [location, *error["loc"]],
                }
                for error in exc.errors()
            ],
        ) from exc


def _build_item_path(key_specs: list[_ColumnSpec]) -> str:
    if len(key_specs) == 1 and key_specs[0].name == "id":
        return "/{id}"
    return "".join(f"/{{{key_spec.name}}}" for key_spec in key_specs)


def _extract_path_key_values(request: Request, key_specs: list[_ColumnSpec]) -> dict[str, Any]:
    return {
        key_spec.name: _coerce_value(
            request.path_params[key_spec.name],
            key_spec.python_type,
            location="path",
        )
        for key_spec in key_specs
    }


def _build_filter_values(
    request: Request,
    filter_specs: dict[str, _ColumnSpec],
) -> dict[str, Any]:
    unknown_filters = sorted(set(request.query_params.keys()) - set(filter_specs) - _RESERVED_QUERY_PARAMS)
    if unknown_filters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported filters: {', '.join(unknown_filters)}",
        )

    return {
        name: _coerce_value(value, filter_specs[name].python_type, location="query")
        for name, value in request.query_params.items()
        if name in filter_specs
    }


async def _fetch_one(
    session: AsyncSession,
    model: type[Any],
    key_values: dict[str, Any],
) -> Any | None:
    statement = select(model)
    for key_name, key_value in key_values.items():
        statement = statement.where(getattr(model, key_name) == key_value)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def _commit_or_conflict(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request violates a database constraint",
        ) from exc


def crud_router(
    *,
    prefix: str,
    model: type[Any],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    read_schema: type[BaseModel],
    tags: list[str] | None = None,
) -> APIRouter:
    """Build the standard CRUD routes for a simple table."""

    mapper = sa_inspect(model)
    key_specs = _build_column_specs(list(mapper.primary_key))
    filter_specs = {
        spec.name: spec
        for spec in _build_column_specs(list(mapper.columns))
        if spec.python_type not in {dict, list, object}
    }
    item_path = _build_item_path(key_specs)
    router = APIRouter(prefix=prefix, tags=tags or [prefix.removeprefix("/")])

    @router.get("/", response_model=list[read_schema])
    async def list_rows(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _: None = Depends(verify_token),
        limit: int = Query(default=100, ge=0, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> list[Any]:
        filter_values = _build_filter_values(request, filter_specs)
        statement = select(model).order_by(*(getattr(model, key_spec.name) for key_spec in key_specs))
        for filter_name, filter_value in filter_values.items():
            statement = statement.where(getattr(model, filter_name) == filter_value)
        result = await session.execute(statement.limit(limit).offset(offset))
        return list(result.scalars().all())

    @router.get(item_path, response_model=read_schema)
    async def get_row(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _: None = Depends(verify_token),
    ) -> Any:
        key_values = _extract_path_key_values(request, key_specs)
        row = await _fetch_one(session, model, key_values)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
        return row

    @router.post("/", response_model=read_schema, status_code=status.HTTP_201_CREATED)
    async def create_row(
        payload: create_schema,
        session: AsyncSession = Depends(get_session),
        _: None = Depends(verify_token),
    ) -> Any:
        row = model(**payload.model_dump(exclude_unset=True))
        session.add(row)
        await _commit_or_conflict(session)
        await session.refresh(row)
        return row

    @router.patch(item_path, response_model=read_schema)
    async def update_row(
        request: Request,
        payload: update_schema,
        session: AsyncSession = Depends(get_session),
        _: None = Depends(verify_token),
    ) -> Any:
        key_values = _extract_path_key_values(request, key_specs)
        row = await _fetch_one(session, model, key_values)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

        update_data = payload.model_dump(exclude_unset=True)
        for key_spec in key_specs:
            if key_spec.name in update_data:
                if update_data[key_spec.name] != key_values[key_spec.name]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{key_spec.name} cannot be updated",
                    )
                update_data.pop(key_spec.name)

        for field_name, field_value in update_data.items():
            setattr(row, field_name, field_value)

        await _commit_or_conflict(session)
        await session.refresh(row)
        return row

    @router.delete(item_path, status_code=status.HTTP_204_NO_CONTENT)
    async def delete_row(
        request: Request,
        session: AsyncSession = Depends(get_session),
        _: None = Depends(verify_token),
    ) -> Response:
        key_values = _extract_path_key_values(request, key_specs)
        row = await _fetch_one(session, model, key_values)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

        await session.delete(row)
        await _commit_or_conflict(session)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


__all__ = ["crud_router"]
