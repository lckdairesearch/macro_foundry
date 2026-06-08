"""CRUD routes for ingestion feeds."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import IngestionFeed
from macro_foundry.schemas import IngestionFeedCreate, IngestionFeedRead, IngestionFeedUpdate

router = crud_router(
    prefix="/ingestion-feeds",
    model=IngestionFeed,
    create_schema=IngestionFeedCreate,
    update_schema=IngestionFeedUpdate,
    read_schema=IngestionFeedRead,
)

__all__ = ["router"]
