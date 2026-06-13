"""CRUD routes for indicator variants."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import IndicatorVariant
from macro_foundry.schemas import IndicatorVariantCreate, IndicatorVariantRead, IndicatorVariantUpdate

router = crud_router(
    prefix="/indicator-variants",
    model=IndicatorVariant,
    create_schema=IndicatorVariantCreate,
    update_schema=IndicatorVariantUpdate,
    read_schema=IndicatorVariantRead,
)

__all__ = ["router"]
