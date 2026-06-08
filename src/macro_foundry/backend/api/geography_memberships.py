"""CRUD routes for geography memberships."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import GeographyMembership
from macro_foundry.schemas import GeographyMembershipCreate, GeographyMembershipRead, GeographyMembershipUpdate

router = crud_router(
    prefix="/geography-memberships",
    model=GeographyMembership,
    create_schema=GeographyMembershipCreate,
    update_schema=GeographyMembershipUpdate,
    read_schema=GeographyMembershipRead,
)

__all__ = ["router"]
