"""Service-layer helpers."""

from macro_foundry.services.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    compose_series_embedding_input,
    embed_text,
    embed_texts,
    hash_embedding_input,
)
from macro_foundry.services.registration import (
    CategoryAttachmentError,
    ensure_category_is_concept,
    ensure_series_embedding_current,
    register_series,
)

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_MODEL",
    "CategoryAttachmentError",
    "compose_series_embedding_input",
    "embed_text",
    "embed_texts",
    "ensure_category_is_concept",
    "ensure_series_embedding_current",
    "hash_embedding_input",
    "register_series",
]
