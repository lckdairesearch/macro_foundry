"""CRUD routes for computation run logs."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import ComputationRunLog
from macro_foundry.schemas import ComputationRunLogCreate, ComputationRunLogRead, ComputationRunLogUpdate

router = crud_router(
    prefix="/computation-run-logs",
    model=ComputationRunLog,
    create_schema=ComputationRunLogCreate,
    update_schema=ComputationRunLogUpdate,
    read_schema=ComputationRunLogRead,
)

__all__ = ["router"]
