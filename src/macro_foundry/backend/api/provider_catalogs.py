"""CRUD routes for provider catalogs."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import ProviderCatalog
from macro_foundry.schemas import ProviderCatalogCreate, ProviderCatalogRead, ProviderCatalogUpdate

router = crud_router(
    prefix="/provider-catalogs",
    model=ProviderCatalog,
    create_schema=ProviderCatalogCreate,
    update_schema=ProviderCatalogUpdate,
    read_schema=ProviderCatalogRead,
)

__all__ = ["router"]
