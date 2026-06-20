"""CRUD routes for source-group members."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import SourceGroupMember
from macro_foundry.schemas import (
    SourceGroupMemberCreate,
    SourceGroupMemberRead,
    SourceGroupMemberUpdate,
)

router = crud_router(
    prefix="/source-group-members",
    model=SourceGroupMember,
    create_schema=SourceGroupMemberCreate,
    update_schema=SourceGroupMemberUpdate,
    read_schema=SourceGroupMemberRead,
)

__all__ = ["router"]
