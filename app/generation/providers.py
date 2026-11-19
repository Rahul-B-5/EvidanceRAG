"""Model-provider boundary for evidence-grounded answer generation."""

from typing import Protocol
from urllib.parse import urlsplit

import httpx
from google import genai
from google.genai import errors, types

from app.core.config import Settings


class GenerationProvider(Protocol):
    """A provider that returns the requested structured JSON response text."""

    def generate_json(self, *, prompt: str, system_instruction: str) -> str:
        ...


class GeminiProvider:
    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
            timeout=int(timeout * 1000), retry_options=types.HttpRetryOptions(attempts=1),
        ))
        self._model = model

    def generate_json(self, *, prompt: str, system_instruction: str) -> str:
        try:
            with self._client as client:
                response = client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
        except (errors.APIError, httpx.HTTPError):
            raise RuntimeError("Gemini did not complete the request. Check the provider configuration and try again.") from None
        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")
        return response.text


class ChatCompletionsProvider:
    def __init__(
        self, *, base_url: str, model: str, api_key: str, timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        try:
            url = urlsplit(base_url)
            local = url.hostname in {"localhost", "127.0.0.1", "::1"}
            if (not url.hostname or url.username or url.password or url.query or url.fragment
                or not (url.scheme == "https" or (url.scheme == "http" and local))):
                raise ValueError
        except ValueError:
            raise RuntimeError("Set GENERATION_BASE_URL to an HTTPS endpoint or a loopback HTTP endpoint.") from None
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.timeout = timeout
        self.transport = transport

    def generate_json(self, *, prompt: str, system_instruction: str) -> str:
        try:
            with httpx.Client(
                timeout=httpx.Timeout(self.timeout, connect=min(10, self.timeout)),
                transport=self.transport, follow_redirects=False, trust_env=False,
            ) as client:
                response = client.post(self.endpoint, headers=self.headers, json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                })
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            raise RuntimeError("Generation provider timed out.") from None
        except httpx.HTTPError:
            raise RuntimeError("Generation provider request failed. Check the server, model and credentials.") from None
        except (KeyError, IndexError, TypeError, ValueError):
            raise RuntimeError("Generation provider returned an invalid response.") from None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Generation provider returned an empty response.")
        return content


def get_generation_provider(settings: Settings) -> GenerationProvider:
    """Build the configured provider without exposing credentials in errors."""
    provider = settings.generation_provider.strip().lower()
    if provider in {"ollama", "openai-compatible", "openai"}:
        if not settings.generation_model.strip():
            raise RuntimeError("Set GENERATION_MODEL to a model supported by your provider.")
        default_urls = {"ollama": "http://127.0.0.1:11434/v1", "openai": "https://api.openai.com/v1"}
        if provider == "openai" and not settings.generation_api_key.strip():
            raise RuntimeError("Set GENERATION_API_KEY for OpenAI.")
        return ChatCompletionsProvider(
            base_url=settings.generation_base_url or default_urls.get(provider, ""),
            model=settings.generation_model.strip(), api_key=settings.generation_api_key.strip(),
            timeout=settings.generation_timeout_seconds,
        )
    if provider != "gemini":
        raise RuntimeError("Unsupported generation provider.")
    if not settings.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Set it in your local .env file."
        )
    return GeminiProvider(
        api_key=settings.gemini_api_key, model=settings.gemini_model,
        timeout=settings.generation_timeout_seconds,
    )
