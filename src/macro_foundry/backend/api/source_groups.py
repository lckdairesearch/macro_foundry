"""CRUD routes for source groups."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import SourceGroup
from macro_foundry.schemas import SourceGroupCreate, SourceGroupRead, SourceGroupUpdate

router = crud_router(
    prefix="/source-groups",
    model=SourceGroup,
    create_schema=SourceGroupCreate,
    update_schema=SourceGroupUpdate,
    read_schema=SourceGroupRead,
)

__all__ = ["router"]
