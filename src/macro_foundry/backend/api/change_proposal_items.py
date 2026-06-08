"""CRUD routes for change proposal items."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import ChangeProposalItem
from macro_foundry.schemas import ChangeProposalItemCreate, ChangeProposalItemRead, ChangeProposalItemUpdate

router = crud_router(
    prefix="/change-proposal-items",
    model=ChangeProposalItem,
    create_schema=ChangeProposalItemCreate,
    update_schema=ChangeProposalItemUpdate,
    read_schema=ChangeProposalItemRead,
)

__all__ = ["router"]
