"""CRUD routes for series sources."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import SeriesSource
from macro_foundry.schemas import SeriesSourceCreate, SeriesSourceRead, SeriesSourceUpdate

router = crud_router(
    prefix="/series-sources",
    model=SeriesSource,
    create_schema=SeriesSourceCreate,
    update_schema=SeriesSourceUpdate,
    read_schema=SeriesSourceRead,
)

__all__ = ["router"]
