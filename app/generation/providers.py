"""Model-provider boundary for evidence-grounded answer generation."""

from typing import Protocol

from google import genai
from google.genai import types

from app.core.config import Settings


class GenerationProvider(Protocol):
    """A provider that returns the requested structured JSON response text."""

    def generate_json(self, *, prompt: str, system_instruction: str) -> str:
        ...


class GeminiProvider:
    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate_json(self, *, prompt: str, system_instruction: str) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")
        return response.text


def get_generation_provider(settings: Settings) -> GenerationProvider:
    """Build the configured provider without exposing credentials in errors."""
    if settings.generation_provider != "gemini":
        raise RuntimeError(
            f"Unsupported generation provider: {settings.generation_provider}."
        )
    if not settings.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Set it in your local .env file."
        )
    return GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
