"""CRUD routes for series family members."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import SeriesFamilyMember
from macro_foundry.schemas import SeriesFamilyMemberCreate, SeriesFamilyMemberRead, SeriesFamilyMemberUpdate

router = crud_router(
    prefix="/series-family-members",
    model=SeriesFamilyMember,
    create_schema=SeriesFamilyMemberCreate,
    update_schema=SeriesFamilyMemberUpdate,
    read_schema=SeriesFamilyMemberRead,
)

__all__ = ["router"]
