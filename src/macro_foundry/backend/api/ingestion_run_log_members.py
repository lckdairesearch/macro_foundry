"""CRUD routes for ingestion run-log member outcomes."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import IngestionRunLogMember
from macro_foundry.schemas import (
    IngestionRunLogMemberCreate,
    IngestionRunLogMemberRead,
    IngestionRunLogMemberUpdate,
)

router = crud_router(
    prefix="/ingestion-run-log-members",
    model=IngestionRunLogMember,
    create_schema=IngestionRunLogMemberCreate,
    update_schema=IngestionRunLogMemberUpdate,
    read_schema=IngestionRunLogMemberRead,
)

__all__ = ["router"]
