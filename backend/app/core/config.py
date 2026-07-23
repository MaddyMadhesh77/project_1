from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root is one level above backend/
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+asyncpg://recovermem:recovermem@localhost:5432/recovermem"
    )

    anthropic_api_key: str | None = None

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Trust decision thresholds (0-100). >=store -> trusted, >=review -> low-trust/review,
    # below review -> reject/quarantine. Configurable so a demo can be tuned live.
    trust_threshold_store: float = 70.0
    trust_threshold_review: float = 40.0

    # Retrieval / ML config, added here in Phase 0 so later phases don't hardcode values.
    retrieval_top_k: int = 5
    min_training_samples: int = 50

    # Cosine-similarity floor for treating a retrieval hit as "the same memory,
    # being updated" rather than an unrelated fact (Phase 2, DESIGN.md 6.3/6.6).
    retrieval_same_memory_threshold: float = 0.5

    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
