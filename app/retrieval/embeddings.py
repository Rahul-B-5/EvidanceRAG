
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Load the configured embedding model once per process."""
    settings = get_settings()
    return SentenceTransformer(settings.embedding_model)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Convert document chunks into normalized embedding vectors."""
    if not texts:
        return []

    if any(not text.strip() for text in texts):
        raise ValueError("Document texts must not contain empty strings.")

    model = get_embedding_model()

    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 16,
    )

    return embeddings.tolist()


def embed_query(text: str) -> list[float]:
    """Convert a search query into a normalized embedding vector."""
    if not text.strip():
        raise ValueError("Query must not be empty.")

    model = get_embedding_model()

    embedding = model.encode(
        text,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    return embedding.tolist()
