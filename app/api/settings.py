"""Expose runtime diagnostics without returning credentials or library content."""

import json
from threading import BoundedSemaphore
from time import perf_counter
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from psycopg import DatabaseError
from psycopg.rows import dict_row
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.db.connection import get_connection
from app.generation.providers import get_generation_provider

router = APIRouter(prefix="/settings", tags=["settings"])
SUPPORTED_PROVIDERS = {"gemini", "anthropic", "openai", "openai-compatible", "ollama"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_probe_slot = BoundedSemaphore(1)
PROBE_PROMPT = 'Reply with the JSON object {"ready": true}.'
PROBE_SYSTEM = "This is a connectivity check. Return only the requested JSON object."


class ProviderStatus(BaseModel):
    provider: str | None
    model: str | None
    transport: Literal["local", "remote"] | None
    configured: bool
    timeout_seconds: float


class IndexStatus(BaseModel):
    model: str
    dimensions: int
    papers: int | None
    passages: int | None
    compatible_vectors: int | None


class RuntimeSettings(BaseModel):
    generation: ProviderStatus
    index: IndexStatus
    database_connected: bool


class ProviderProbe(BaseModel):
    elapsed_ms: int


class ProbeRequest(BaseModel):
    synthetic: Literal[True]


def describe_provider(settings: Settings) -> dict:
    kind = settings.generation_provider.strip().lower()
    known = kind in SUPPORTED_PROVIDERS
    model = settings.gemini_model if kind == "gemini" else settings.generation_model
    ready = False
    transport = None
    if known:
        try:
            get_generation_provider(settings)
            if kind in {"gemini", "anthropic"}:
                transport = "remote"
            elif settings.generation_base_url:
                transport = "local" if urlsplit(settings.generation_base_url).hostname in LOCAL_HOSTS else "remote"
            else:
                transport = "local" if kind == "ollama" else "remote"
            ready = True
        except (RuntimeError, ValueError):
            pass
    return {"provider":kind if known else None, "model":(model.strip() or None) if known else None,
            "transport":transport, "configured":ready, "timeout_seconds":settings.generation_timeout_seconds}


@router.get("", response_model=RuntimeSettings)
def runtime_settings() -> dict:
    config = get_settings()
    connected = False
    counts = {"papers":None, "passages":None, "compatible_vectors":None}
    try:
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
            counts = cursor.execute("""
                SELECT (SELECT count(*) FROM documents) AS papers,
                       count(*) AS passages,
                       count(*) FILTER (
                           WHERE embedding IS NOT NULL AND embedding_model=%s AND embedding_dimensions=%s
                       ) AS compatible_vectors
                FROM chunks
            """, (config.embedding_model, config.embedding_dimensions)).fetchone()
        connected = True
    except DatabaseError:
        pass
    return {"generation":describe_provider(config),
            "index":{**counts, "model":config.embedding_model, "dimensions":config.embedding_dimensions},
            "database_connected":connected}


@router.post("/test-provider", response_model=ProviderProbe)
def test_configured_provider(_request: ProbeRequest) -> dict:
    if not _probe_slot.acquire(blocking=False):
        raise HTTPException(409, "A provider check is already running.")
    started = perf_counter()
    try:
        config = get_settings()
        provider = get_generation_provider(config.model_copy(update={
            "generation_timeout_seconds": min(config.generation_timeout_seconds, 15),
        }))
        result = json.loads(provider.generate_json(prompt=PROBE_PROMPT, system_instruction=PROBE_SYSTEM))
        if not isinstance(result, dict) or result.get("ready") is not True:
            raise ValueError
        return {"elapsed_ms":round((perf_counter() - started) * 1000)}
    except (RuntimeError, ValueError, TypeError):
        raise HTTPException(503, "The provider did not complete the JSON check. Check its model and configuration.") from None
    finally:
        _probe_slot.release()
