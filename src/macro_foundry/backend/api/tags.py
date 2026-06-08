"""CRUD routes for tags."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import Tag
from macro_foundry.schemas import TagCreate, TagRead, TagUpdate

router = crud_router(
    prefix="/tags",
    model=Tag,
    create_schema=TagCreate,
    update_schema=TagUpdate,
    read_schema=TagRead,
)

__all__ = ["router"]
