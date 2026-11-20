"""Serve the application for browser tests with deterministic model fixtures."""

import os
from types import SimpleNamespace
from unittest.mock import patch

import uvicorn

from app.api.main import app
from app.db.connection import get_connection
from evaluation.database import BROWSER_TABLES, assert_isolated


def main() -> None:
    schema = os.environ["EVIDENCERAG_E2E_SCHEMA"]
    with get_connection() as conn:
        assert_isolated(conn, schema, BROWSER_TABLES)
    provider = SimpleNamespace(
        generate_json=lambda **_: '{"answer":"The held-out sample contains 37 observations [E1].","abstained":false,"reason":null}',
    )
    def embeddings(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] if "37 observations" in text else [0.0, 1.0, 0.0] for text in texts]
    with (
        patch("app.ingestion.pipeline.embed_documents", embeddings),
        patch("app.retrieval.reembedding.embed_documents", embeddings),
        patch("app.retrieval.vector.embed_query", return_value=[1.0, 0.0, 0.0]),
        patch("app.generation.answerer.get_generation_provider", return_value=provider),
        patch("app.api.settings.get_generation_provider",
              return_value=SimpleNamespace(generate_json=lambda **_: '{"ready":true}')),
    ):
        uvicorn.run(app, host="127.0.0.1", port=int(os.environ["EVIDENCERAG_E2E_API_PORT"]), access_log=False)


if __name__ == "__main__":
    main()
