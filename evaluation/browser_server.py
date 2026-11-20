"""Serve the application for browser tests with deterministic model fixtures."""

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import uvicorn
from fastapi import HTTPException, Request

from app.api.main import app
from app.db.connection import get_connection
from app.generation.profile_store import active_settings
from app.generation.providers import get_generation_provider
from evaluation.database import BROWSER_TABLES, assert_isolated


def main() -> None:
    schema = os.environ["EVIDENCERAG_E2E_SCHEMA"]
    with get_connection() as conn:
        assert_isolated(conn, schema, BROWSER_TABLES)
        legacy = conn.execute(
            "INSERT INTO conversations (title) VALUES ('Legacy browser conversation') RETURNING id",
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'assistant', 'Archived calibration summary.')",
            (legacy,),
        )
    provider = SimpleNamespace(
        generate_json=lambda **_: '{"answer":"The held-out sample contains 37 observations [E1].","abstained":false,"reason":null}',
    )
    installed = ["fixture:one", "fixture:two"]

    @app.get("/api/tags")
    def fixture_models():
        return {"models": [{"name": model} for model in installed]}

    @app.post("/v1/chat/completions")
    async def fixture_completion(request: Request):
        payload = await request.json()
        model = payload["model"]
        if model not in installed:
            raise HTTPException(404, "Model not installed.")
        output = ({"ready": True} if "synthetic connectivity check" in payload["messages"][0]["content"] else
                  {"answer": f"Model {model} reports 37 observations [E1].", "abstained": False, "reason": None})
        return {"choices":[{"message":{"content":json.dumps(output)}}]}

    def answer_provider(settings):
        active = active_settings(settings, "answer")
        return provider if active is settings else get_generation_provider(active)

    def embeddings(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] if "37 observations" in text else [0.0, 1.0, 0.0] for text in texts]
    with (
        patch("app.ingestion.pipeline.embed_documents", embeddings),
        patch("app.retrieval.reembedding.embed_documents", embeddings),
        patch("app.retrieval.vector.embed_query", return_value=[1.0, 0.0, 0.0]),
        patch("app.generation.answerer.get_generation_provider", side_effect=answer_provider),
        patch("research.structured.get_generation_provider",
              return_value=SimpleNamespace(generate_json=lambda **_: (
                  '{"findings":[{"topic":"results","source":1,"method":"StarlingNet",'
                  '"metric":"F1 score","value":"87%","dataset":"OrchardBench"}]}'
              ))),
        patch("app.api.settings.get_generation_provider",
              return_value=SimpleNamespace(generate_json=lambda **_: '{"ready":true}')),
    ):
        uvicorn.run(app, host="127.0.0.1", port=int(os.environ["EVIDENCERAG_E2E_API_PORT"]), access_log=False)


if __name__ == "__main__":
    main()
