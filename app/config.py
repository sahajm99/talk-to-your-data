"""Configuration management using environment variables."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenAI Configuration
    openai_api_key: str

    # Weaviate Configuration
    weaviate_url: str = "http://localhost:8080"
    weaviate_api_key: Optional[str] = None
    weaviate_class_name: str = "IngestedChunk"  # Configurable class name

    # Chunking Configuration
    chunk_max_tokens: int = 400
    chunk_overlap_tokens: int = 50

    # Data Storage Configuration (Phase 1)
    data_dir: str = "./data"  # Base directory for storing documents and images
    use_visual_grounding: bool = True  # Enable/disable visual grounding

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Singleton settings instance
settings = Settings()

