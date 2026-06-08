"""CRUD routes for change proposals."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import ChangeProposal
from macro_foundry.schemas import ChangeProposalCreate, ChangeProposalRead, ChangeProposalUpdate

router = crud_router(
    prefix="/change-proposals",
    model=ChangeProposal,
    create_schema=ChangeProposalCreate,
    update_schema=ChangeProposalUpdate,
    read_schema=ChangeProposalRead,
)

__all__ = ["router"]
