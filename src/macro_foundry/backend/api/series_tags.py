"""CRUD routes for series tags."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import SeriesTag
from macro_foundry.schemas import SeriesTagCreate, SeriesTagRead, SeriesTagUpdate

router = crud_router(
    prefix="/series-tags",
    model=SeriesTag,
    create_schema=SeriesTagCreate,
    update_schema=SeriesTagUpdate,
    read_schema=SeriesTagRead,
)

__all__ = ["router"]
