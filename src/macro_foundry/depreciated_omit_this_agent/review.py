"""Reviewer output models for governance and data_correctness review nodes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

ReviewSpecialty = Literal["governance", "data_correctness"]


class ReviewBundle(BaseModel):
    """Findings from one reviewer node for one review cycle."""

    model_config = ConfigDict(frozen=True)

    specialty: ReviewSpecialty
    findings: tuple[str, ...] = ()
    review_cycle: int
    bounce_to_drafter: bool

    def __init__(self, **data: object) -> None:
        if "findings" in data and isinstance(data["findings"], list):
            data["findings"] = tuple(data["findings"])
        super().__init__(**data)


__all__ = ["ReviewBundle", "ReviewSpecialty"]
