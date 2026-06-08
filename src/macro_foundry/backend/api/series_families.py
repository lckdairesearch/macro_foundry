"""CRUD routes for series families."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import SeriesFamily
from macro_foundry.schemas import SeriesFamilyCreate, SeriesFamilyRead, SeriesFamilyUpdate

router = crud_router(
    prefix="/series-families",
    model=SeriesFamily,
    create_schema=SeriesFamilyCreate,
    update_schema=SeriesFamilyUpdate,
    read_schema=SeriesFamilyRead,
)

__all__ = ["router"]
