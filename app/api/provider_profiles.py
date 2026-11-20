"""Configure generation from the local browser without returning credentials."""

import json
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, SecretStr

from app.core.config import get_settings
from app.db.connection import get_connection
from app.generation.profile_store import credential_cipher, profile_settings, read_profile
from app.generation.providers import get_generation_provider

Purpose = Literal["answer", "extraction"]
Kind = Literal["ollama", "openai", "anthropic", "gemini", "openai-compatible"]
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class PrivateValidationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, "Check the provider fields and try again.") from None

        return safe_handler


router = APIRouter(prefix="/settings/providers", route_class=PrivateValidationRoute)


class ProfileEdit(BaseModel):
    provider: Kind
    model: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:/-]*$")
    endpoint: str = Field(default="", max_length=400)
    api_key: SecretStr | None = Field(default=None, max_length=4096)
    revision: int = Field(default=0, ge=0)
    clear_key: bool = False
    ollama_context_tokens: int | None = Field(default=None, ge=2048, le=65536)


class OllamaEndpoint(BaseModel):
    endpoint: str = Field(default="", max_length=400)


def local_access(request: Request) -> None:
    try:
        client_ok = bool(request.client and ip_address(request.client.host).is_loopback)
        origin = request.headers.get("origin")
        origin_ok = origin is None or urlsplit(origin).hostname in LOOPBACK
    except ValueError:
        client_ok = origin_ok = False
    if not client_ok or not origin_ok:
        raise HTTPException(403, "Provider configuration is available only on this computer.")


def normalized_endpoint(provider: str, endpoint: str) -> str:
    endpoint = endpoint.strip().rstrip("/")
    if provider not in {"ollama", "openai-compatible"}:
        if endpoint:
            raise HTTPException(422, "This provider uses its official endpoint.")
        return ""
    if provider == "ollama" and not endpoint:
        return "http://127.0.0.1:11434/v1"
    try:
        url = urlsplit(endpoint)
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError
        port = url.port
        if provider == "ollama":
            if url.hostname not in LOOPBACK or url.scheme not in {"http", "https"} or url.path not in {"", "/v1"}:
                raise ValueError
            host = "[::1]" if url.hostname == "::1" else "127.0.0.1"
            authority = f"{host}:{port}" if port is not None else host
            return f"{url.scheme}://{authority}/v1"
        if url.scheme == "https" or (url.scheme == "http" and url.hostname in LOOPBACK):
            return endpoint
    except ValueError:
        pass
    raise HTTPException(422, "Enter a loopback Ollama URL or an HTTPS-compatible API URL.")


def public_profile(profile: dict | None) -> dict | None:
    if profile is None:
        return None
    return {key: profile[key] for key in ("provider", "model", "endpoint", "revision", "ollama_context_tokens")} | {
        "has_key": bool(profile["credential"]),
    }


def draft_profile(edit: ProfileEdit, previous: dict | None, *, create_key: bool) -> dict:
    endpoint = normalized_endpoint(edit.provider, edit.endpoint)
    if edit.provider != "ollama" and edit.ollama_context_tokens is not None:
        raise HTTPException(422, "A local context size can only be set for Ollama.")
    key = edit.api_key.get_secret_value().strip() if edit.api_key else ""
    credential = None
    if key and not edit.clear_key:
        if edit.provider == "ollama":
            raise HTTPException(422, "Local Ollama does not use an API key.")
        credential = credential_cipher(get_settings().provider_key_path, create=True).encrypt(key.encode()) if create_key else None
    elif previous and not edit.clear_key and previous["provider"] == edit.provider and previous["endpoint"] == endpoint:
        credential = previous["credential"]
    if edit.provider in {"openai", "anthropic", "gemini"} and not (credential or (key and not edit.clear_key)):
        raise HTTPException(422, "Enter an API key for this provider.")
    return {"provider": edit.provider, "model": edit.model, "endpoint": endpoint,
            "credential": credential, "ollama_context_tokens": edit.ollama_context_tokens}


@router.get("")
def profiles(request: Request) -> dict:
    local_access(request)
    with get_connection() as conn:
        return {purpose: public_profile(read_profile(conn, purpose)) for purpose in ("answer", "extraction")}


@router.put("/{purpose}")
def save_profile(purpose: Purpose, edit: ProfileEdit, request: Request) -> dict:
    local_access(request)
    with get_connection() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(4961347, CASE WHEN %s = 'answer' THEN 1 ELSE 2 END)", (purpose,))
        previous = read_profile(conn, purpose)
        if edit.revision != (previous["revision"] if previous else 0):
            raise HTTPException(409, "Provider settings changed. Reload them and try again.")
        try:
            profile = draft_profile(edit, previous, create_key=True)
        except RuntimeError as error:
            raise HTTPException(503, str(error)) from None
        revision = conn.execute("""
            INSERT INTO generation_profiles (purpose,provider,model,endpoint,credential,ollama_context_tokens)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (purpose) DO UPDATE SET provider=EXCLUDED.provider, model=EXCLUDED.model,
                endpoint=EXCLUDED.endpoint, credential=EXCLUDED.credential,
                ollama_context_tokens=EXCLUDED.ollama_context_tokens, revision=generation_profiles.revision+1
            RETURNING revision
        """, (purpose, profile["provider"], profile["model"], profile["endpoint"], profile["credential"],
              profile["ollama_context_tokens"])).fetchone()[0]
    return public_profile({**profile, "revision": revision})


@router.post("/ollama/models")
def ollama_models(draft: OllamaEndpoint, request: Request) -> dict:
    local_access(request)
    endpoint = normalized_endpoint("ollama", draft.endpoint)
    try:
        with httpx.Client(timeout=4, follow_redirects=False, trust_env=False) as client:
            response = client.get(endpoint.removesuffix("/v1") + "/api/tags")
            response.raise_for_status()
            return {"models": sorted({item["name"] for item in response.json()["models"]
                                      if isinstance(item, dict) and isinstance(item.get("name"), str)})}
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        raise HTTPException(503, "Could not list Ollama models. Start Ollama and check the endpoint.") from None


@router.post("/{purpose}/test")
def test_profile(purpose: Purpose, edit: ProfileEdit, request: Request) -> dict:
    local_access(request)
    with get_connection() as conn:
        previous = read_profile(conn, purpose)
    try:
        profile = draft_profile(edit, previous, create_key=False)
        settings = profile_settings(get_settings(), profile)
        key = edit.api_key.get_secret_value().strip() if edit.api_key and not edit.clear_key else ""
        if key:
            settings = settings.model_copy(update={"generation_api_key": key, "gemini_api_key": key})
        provider = get_generation_provider(settings.model_copy(update={"generation_timeout_seconds": 20}))
        schema = {"type": "object", "properties": {"ready": {"type": "boolean"}},
                  "required": ["ready"], "additionalProperties": False}
        result = json.loads(provider.generate_json(
            prompt='Return {"ready":true}.', system_instruction="Return a JSON object for this synthetic connectivity check.",
            schema=schema if purpose == "answer" else None,
        ))
        if not isinstance(result, dict) or result.get("ready") is not True:
            raise ValueError
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from None
    except (ValueError, TypeError):
        raise HTTPException(503, "The model did not return the requested JSON object.") from None
    return {"ready": True}
