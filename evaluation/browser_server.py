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


def fixture_answer(prompt: str, model: str | None = None) -> dict:
    data = json.loads(prompt)
    if "without tuning in Table 2" in data["question"]:
        table = next(item for item in data["evidence"] if "table_row" in item)
        score = next(cell["value"] for cell in table["table_row"]["cells"] if cell["column"] == "Score")
        answer = f"Table 2 reports a score of {score} [{table['evidence_id']}]."
    elif model:
        answer = f"Model {model} reports 37 observations [E1]."
    else:
        answer = "The held-out sample contains 37 observations [E1]."
    return {"answer": answer, "abstained": False, "reason": None}


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
    provider = SimpleNamespace(generate_json=lambda *, prompt, **_: json.dumps(fixture_answer(prompt)))
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
                  fixture_answer(payload["messages"][-1]["content"], model))
        return {"choices":[{"message":{"content":json.dumps(output)}}]}

    @app.post("/api/chat")
    async def fixture_context_chat(request: Request):
        payload = await request.json()
        model = payload["model"]
        if model not in installed:
            raise HTTPException(404, "Model not installed.")
        if payload["options"]["num_ctx"] != 8192:
            raise HTTPException(400, "Expected the configured context size.")
        output = ({"ready": True} if "synthetic connectivity check" in payload["messages"][0]["content"] else
                  fixture_answer(payload["messages"][-1]["content"], model))
        return {"message":{"content":json.dumps(output)}, "done": True}

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
