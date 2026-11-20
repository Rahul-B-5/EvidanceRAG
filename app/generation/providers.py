"""Model-provider boundary for evidence-grounded answer generation."""

from typing import Protocol
from urllib.parse import urlsplit

import httpx
from google import genai
from google.genai import errors, types

from app.core.config import Settings
from app.generation import profile_store


class GenerationProvider(Protocol):
    """A provider that returns the requested structured JSON response text."""

    def generate_json(self, *, prompt: str, system_instruction: str, schema: dict | None = None) -> str:
        ...


class GeminiProvider:
    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        self._api_key = api_key
        self._http_options = types.HttpOptions(
            timeout=int(timeout * 1000), retry_options=types.HttpRetryOptions(attempts=1),
        )
        self._model = model

    def generate_json(self, *, prompt: str, system_instruction: str, schema: dict | None = None) -> str:
        try:
            with genai.Client(api_key=self._api_key, http_options=self._http_options) as client:
                response = client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_json_schema=schema,
                        temperature=0.1,
                    ),
                )
        except (errors.APIError, httpx.HTTPError):
            raise RuntimeError("Gemini did not complete the request. Check the provider configuration and try again.") from None
        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")
        return response.text


class AnthropicProvider:
    def __init__(self, *, model: str, api_key: str, timeout: float, transport: httpx.BaseTransport | None = None):
        self.model = model
        self._api_key = api_key
        self.timeout = timeout
        self.transport = transport

    def generate_json(self, *, prompt: str, system_instruction: str, schema: dict | None = None) -> str:
        payload = {
            "model": self.model, "max_tokens": 4096,
            "system": system_instruction + "\nOutput a JSON object without Markdown fences.",
            "messages": [{"role": "user", "content": prompt}],
        }
        if schema is not None:
            payload["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport, trust_env=False,
                              follow_redirects=False) as client:
                response = client.post("https://api.anthropic.com/v1/messages", json=payload, headers={
                    "x-api-key": self._api_key, "anthropic-version": "2023-06-01",
                })
                response.raise_for_status()
                data = response.json()
                if data["stop_reason"] in {"max_tokens", "refusal"}:
                    raise RuntimeError("Claude did not finish a usable JSON response.")
                answer = "".join(block["text"] for block in data["content"] if block["type"] == "text")
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            message = {
                400: "Claude rejected the request. Check whether the model supports the requested JSON format.",
                401: "Claude rejected the API key.",
                403: "The Claude API key cannot access this model.",
                404: "The Claude model was not found.",
                429: "Claude rate limit reached. Try again later.",
            }.get(status, "Claude did not complete the request. Try again later.")
            raise RuntimeError(message) from None
        except httpx.HTTPError:
            raise RuntimeError("Cannot reach Claude. Check connectivity and try again.") from None
        except (TypeError, ValueError, KeyError):
            raise RuntimeError("Claude returned an invalid response.") from None
        if not answer.strip():
            raise RuntimeError("Claude returned an empty response.")
        return answer


class ChatCompletionsProvider:
    def __init__(
        self, *, base_url: str, model: str, api_key: str, timeout: float,
        transport: httpx.BaseTransport | None = None,
        reasoning_effort: str = "",
        structured_outputs: bool = False,
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
        self.reasoning_effort = reasoning_effort
        self.structured_outputs = structured_outputs

    def generate_json(self, *, prompt: str, system_instruction: str, schema: dict | None = None) -> str:
        response_format = {"type": "json_object"}
        if self.structured_outputs and schema is not None:
            response_format = {"type": "json_schema", "json_schema": {
                "name": "evidence_answer", "strict": True, "schema": schema,
            }}
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
                    "response_format": response_format,
                    **({"temperature": 0.1} if self.structured_outputs and schema is not None else {}),
                    **({"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}),
                })
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException:
            raise RuntimeError("Generation provider timed out.") from None
        except httpx.HTTPStatusError as error:
            detail = {
                400: "Check whether the server and model support JSON output.",
                401: "The API key was rejected.",
                403: "The API key cannot access this model.",
                404: "The model or API route was not found.",
                429: "The provider rate limit was reached.",
            }.get(error.response.status_code, "Check the server, model and credentials.")
            raise RuntimeError(f"Generation provider request failed. {detail}") from None
        except httpx.HTTPError:
            raise RuntimeError("Generation provider request failed. Check the server, model and credentials.") from None
        except (KeyError, IndexError, TypeError, ValueError):
            raise RuntimeError("Generation provider returned an invalid response.") from None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Generation provider returned an empty response.")
        return content


class OllamaContextProvider:
    def __init__(self, *, base_url: str, model: str, timeout: float, context_tokens: int,
                 reasoning_effort: str, transport: httpx.BaseTransport | None = None):
        endpoint = base_url.rstrip("/")
        try:
            url = urlsplit(endpoint)
            if (url.hostname not in {"127.0.0.1", "localhost", "::1"} or url.scheme not in {"http", "https"}
                    or url.path not in {"", "/v1"} or url.username or url.password or url.query or url.fragment):
                raise ValueError
            _ = url.port
        except ValueError:
            raise RuntimeError("A custom Ollama context requires a loopback Ollama URL.") from None
        self.endpoint = endpoint.removesuffix("/v1") + "/api/chat"
        self.model = model
        self.timeout = timeout
        self.context_tokens = context_tokens
        self.reasoning_effort = reasoning_effort
        self.transport = transport

    def generate_json(self, *, prompt: str, system_instruction: str, schema: dict | None = None) -> str:
        payload = {
            "model": self.model, "stream": False, "format": schema if schema is not None else "json",
            "messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
            "options": {"num_ctx": self.context_tokens, "temperature": 0.1},
        }
        if self.reasoning_effort:
            payload["think"] = False if self.reasoning_effort == "none" else self.reasoning_effort
        try:
            with httpx.Client(timeout=httpx.Timeout(self.timeout, connect=min(10, self.timeout)),
                              transport=self.transport, follow_redirects=False, trust_env=False) as client:
                response = client.post(self.endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
                content = data["message"]["content"]
        except httpx.TimeoutException:
            raise RuntimeError("Ollama timed out. Check the context size and available memory.") from None
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                raise RuntimeError("The Ollama model or native API route was not found.") from None
            raise RuntimeError("Ollama rejected the chat request. Check the model and context size.") from None
        except httpx.HTTPError:
            raise RuntimeError("Cannot reach Ollama. Check its local endpoint.") from None
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("Ollama returned an invalid response.") from None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Ollama returned an empty response.")
        return content


def get_generation_provider(settings: Settings) -> GenerationProvider:
    """Build the configured provider without exposing credentials in errors."""
    provider = settings.generation_provider.strip().lower()
    if provider == "anthropic":
        if not settings.generation_model.strip() or not settings.generation_api_key.strip():
            raise RuntimeError("Configure a Claude model and API key.")
        return AnthropicProvider(model=settings.generation_model.strip(),
                                 api_key=settings.generation_api_key.strip(),
                                 timeout=settings.generation_timeout_seconds)
    if provider in {"ollama", "openai-compatible", "openai"}:
        if not settings.generation_model.strip():
            raise RuntimeError("Set GENERATION_MODEL to a model supported by your provider.")
        default_urls = {"ollama": "http://127.0.0.1:11434/v1", "openai": "https://api.openai.com/v1"}
        if provider == "openai" and not settings.generation_api_key.strip():
            raise RuntimeError("Set GENERATION_API_KEY for OpenAI.")
        base_url = settings.generation_base_url or default_urls.get(provider, "")
        if provider == "ollama" and settings.ollama_context_tokens is not None:
            return OllamaContextProvider(
                base_url=base_url, model=settings.generation_model.strip(), timeout=settings.generation_timeout_seconds,
                context_tokens=settings.ollama_context_tokens, reasoning_effort=settings.ollama_reasoning_effort,
            )
        return ChatCompletionsProvider(
            base_url=base_url,
            model=settings.generation_model.strip(), api_key=settings.generation_api_key.strip(),
            timeout=settings.generation_timeout_seconds,
            reasoning_effort=settings.ollama_reasoning_effort if provider == "ollama" else "",
            structured_outputs=provider == "ollama",
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


def get_answer_provider(defaults: Settings) -> GenerationProvider:
    return get_generation_provider(profile_store.active_settings(defaults, "answer"))


def get_extraction_provider(defaults: Settings) -> GenerationProvider:
    return get_generation_provider(profile_store.active_settings(defaults, "extraction"))
