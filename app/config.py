"""Application settings (pydantic-settings, read from the environment and `.env`)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Field names map to upper-case environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Generation (Groq; without a key the app answers extractively)
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_fallback_model: str = "llama-3.1-8b-instant"

    # Embeddings ("fake" selects the deterministic FakeEmbedder)
    embed_model: str = "BAAI/bge-small-en-v1.5"

    # Storage
    data_dir: Path = Path("data")
    index_path: Path = Path("data/index.db")

    # Chunking and retrieval
    chunk_max_tokens: int = 300
    chunk_overlap_tokens: int = 50
    top_k: int = 5
    candidates_per_source: int = 20

    # Abuse limits
    rate_limit_questions: int = 10
    rate_limit_window_seconds: int = 600
    daily_question_cap: int = 500
    max_upload_bytes: int = 2_000_000
    session_ttl_minutes: int = 60

    # Deployment
    public_url: str = ""


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings instance."""
    return Settings()
