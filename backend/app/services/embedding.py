from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings


class EmbeddingService:
    """Wraps a sentence-transformers model. Swappable by model name (DESIGN.md 6.2)."""

    def __init__(self, model_name: str) -> None:
        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()


@lru_cache
def get_embedding_service() -> EmbeddingService:
    # Cached per-process (see main.py's lifespan, which warms this at
    # startup) -- but per-*process*, not per-machine: `uvicorn --workers N`
    # runs N separate OS processes, each getting its own independent copy of
    # this model in memory (see README's "Running locally" note). There's no
    # cross-process sharing here; scale by running multiple single-worker
    # instances, not by adding worker processes to one.
    return EmbeddingService(get_settings().embedding_model)
