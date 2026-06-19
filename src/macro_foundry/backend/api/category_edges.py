"""CRUD routes for category-tree edges."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import CategoryEdge
from macro_foundry.schemas import CategoryEdgeCreate, CategoryEdgeRead, CategoryEdgeUpdate

router = crud_router(
    prefix="/category-edges",
    model=CategoryEdge,
    create_schema=CategoryEdgeCreate,
    update_schema=CategoryEdgeUpdate,
    read_schema=CategoryEdgeRead,
)

__all__ = ["router"]
