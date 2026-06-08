"""CRUD routes for providers."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import Provider
from macro_foundry.schemas import ProviderCreate, ProviderRead, ProviderUpdate

router = crud_router(
    prefix="/providers",
    model=Provider,
    create_schema=ProviderCreate,
    update_schema=ProviderUpdate,
    read_schema=ProviderRead,
)

__all__ = ["router"]
