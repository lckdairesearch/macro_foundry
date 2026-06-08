"""CRUD routes for geographies."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import Geography
from macro_foundry.schemas import GeographyCreate, GeographyRead, GeographyUpdate

router = crud_router(
    prefix="/geographies",
    model=Geography,
    create_schema=GeographyCreate,
    update_schema=GeographyUpdate,
    read_schema=GeographyRead,
)

__all__ = ["router"]
