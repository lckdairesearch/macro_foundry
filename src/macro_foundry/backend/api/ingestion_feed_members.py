"""CRUD routes for ingestion feed members."""

from macro_foundry.backend.crud import crud_router
from macro_foundry.models import IngestionFeedMember
from macro_foundry.schemas import IngestionFeedMemberCreate, IngestionFeedMemberRead, IngestionFeedMemberUpdate

router = crud_router(
    prefix="/ingestion-feed-members",
    model=IngestionFeedMember,
    create_schema=IngestionFeedMemberCreate,
    update_schema=IngestionFeedMemberUpdate,
    read_schema=IngestionFeedMemberRead,
)

__all__ = ["router"]
