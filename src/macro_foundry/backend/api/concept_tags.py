"""CRUD routes for concept tags."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import ConceptTag
from macro_foundry.schemas import ConceptTagCreate, ConceptTagRead, ConceptTagUpdate

router = crud_router(
    prefix="/concept-tags",
    model=ConceptTag,
    create_schema=ConceptTagCreate,
    update_schema=ConceptTagUpdate,
    read_schema=ConceptTagRead,
)

__all__ = ["router"]
