"""Minimal pgvector column type without an extra package dependency."""

from __future__ import annotations

from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    """Represent a Postgres `vector(N)` column as `list[float]`."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect: object) -> object:
        del dialect

        def process(value: list[float] | tuple[float, ...] | None) -> str | None:
            if value is None:
                return None
            return "[" + ",".join(str(float(item)) for item in value) + "]"

        return process

    def result_processor(self, dialect: object, coltype: object) -> object:
        del dialect, coltype

        def process(value: object) -> list[float] | None:
            if value is None:
                return None
            if isinstance(value, str):
                stripped = value.strip()[1:-1]
                if not stripped:
                    return []
                return [float(part) for part in stripped.split(",")]
            if isinstance(value, list):
                return [float(item) for item in value]
            if isinstance(value, tuple):
                return [float(item) for item in value]
            raise TypeError(f"Unexpected vector value type: {type(value)!r}")

        return process
