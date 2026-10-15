
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/evidencerag",
        alias="DATABASE_URL",
    )
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        alias="EMBEDDING_MODEL",
    )
    embedding_dimensions: int = Field(
        default=384,
        alias="EMBEDDING_DIMENSIONS",
    )
    gemini_api_key: str | None = Field(
        default=None,
        alias="GEMINI_API_KEY",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        alias="GEMINI_MODEL",
    )
    upload_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "uploads",
        alias="UPLOAD_DIR",
    )
    max_upload_mb: int = Field(default=25, alias="MAX_UPLOAD_MB")
    chunk_size: int = Field(default=1800, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=250, alias="CHUNK_OVERLAP")
    retrieval_top_k: int = Field(default=5, alias="RETRIEVAL_TOP_K")

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    if settings.embedding_dimensions <= 0:
        raise ValueError("EMBEDDING_DIMENSIONS must be positive.")

    if settings.chunk_size <= 0:
        raise ValueError("CHUNK_SIZE must be positive.")

    if not 0 <= settings.chunk_overlap < settings.chunk_size:
        raise ValueError(
            "CHUNK_OVERLAP must be non-negative and smaller than CHUNK_SIZE."
        )

    if settings.max_upload_mb <= 0:
        raise ValueError("MAX_UPLOAD_MB must be positive.")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return settings
