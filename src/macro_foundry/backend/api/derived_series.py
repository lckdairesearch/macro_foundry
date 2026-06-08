"""CRUD routes for derived series."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import DerivedSeries
from macro_foundry.schemas import DerivedSeriesCreate, DerivedSeriesRead, DerivedSeriesUpdate

router = crud_router(
    prefix="/derived-series",
    model=DerivedSeries,
    create_schema=DerivedSeriesCreate,
    update_schema=DerivedSeriesUpdate,
    read_schema=DerivedSeriesRead,
)

__all__ = ["router"]
