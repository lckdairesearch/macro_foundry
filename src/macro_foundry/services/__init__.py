"""Service-layer helpers."""

from macro_foundry.services.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    compose_concept_embedding_input,
    compose_indicator_embedding_input,
    compose_series_embedding_input,
    embed_text,
    embed_texts,
    hash_embedding_input,
)
from macro_foundry.services.registration import (
    ensure_series_embedding_current,
    register_concept,
    register_indicator,
    register_series,
)

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_MODEL",
    "compose_concept_embedding_input",
    "compose_indicator_embedding_input",
    "compose_series_embedding_input",
    "embed_text",
    "embed_texts",
    "hash_embedding_input",
    "ensure_series_embedding_current",
    "register_concept",
    "register_indicator",
    "register_series",
]
