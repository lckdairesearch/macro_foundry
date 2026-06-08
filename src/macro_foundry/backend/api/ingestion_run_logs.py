"""CRUD routes for ingestion run logs."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import IngestionRunLog
from macro_foundry.schemas import IngestionRunLogCreate, IngestionRunLogRead, IngestionRunLogUpdate

router = crud_router(
    prefix="/ingestion-run-logs",
    model=IngestionRunLog,
    create_schema=IngestionRunLogCreate,
    update_schema=IngestionRunLogUpdate,
    read_schema=IngestionRunLogRead,
)

__all__ = ["router"]
