"""CRUD routes for series families."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import Indicator
from macro_foundry.schemas import IndicatorCreate, IndicatorRead, IndicatorUpdate

router = crud_router(
    prefix="/series-families",
    model=Indicator,
    create_schema=IndicatorCreate,
    update_schema=IndicatorUpdate,
    read_schema=IndicatorRead,
)

__all__ = ["router"]
