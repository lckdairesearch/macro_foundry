"""CRUD routes for concepts."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import Concept
from macro_foundry.schemas import ConceptCreate, ConceptRead, ConceptUpdate

router = crud_router(
    prefix="/concepts",
    model=Concept,
    create_schema=ConceptCreate,
    update_schema=ConceptUpdate,
    read_schema=ConceptRead,
)

__all__ = ["router"]
