"""CRUD routes for derivation inputs."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import DerivationInput
from macro_foundry.schemas import DerivationInputCreate, DerivationInputRead, DerivationInputUpdate

router = crud_router(
    prefix="/derivation-inputs",
    model=DerivationInput,
    create_schema=DerivationInputCreate,
    update_schema=DerivationInputUpdate,
    read_schema=DerivationInputRead,
)

__all__ = ["router"]
