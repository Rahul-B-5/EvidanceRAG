import json

import httpx
import pytest

from app.core.config import Settings
from app.generation.providers import ChatCompletionsProvider, GeminiProvider, get_generation_provider


def test_chat_completions_sends_json_mode_with_system_role():
    def handle(request):
        assert request.url == "https://example.com/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer fixture"
        body = json.loads(request.content)
        assert body["model"] == "fixture-model"
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"] == [
            {"role": "system", "content": "Use evidence"},
            {"role": "user", "content": "Synthetic passage"},
        ]
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    provider = ChatCompletionsProvider(
        base_url="https://example.com/v1/", model="fixture-model", api_key="fixture",
        timeout=1, transport=httpx.MockTransport(handle),
    )
    assert provider.generate_json(prompt="Synthetic passage", system_instruction="Use evidence") == "{}"


@pytest.mark.parametrize("url", ["http://example.com/v1", "https://a:b@example.com/v1", "file:///tmp/model"])
def test_rejects_unsafe_provider_urls(url):
    with pytest.raises(RuntimeError, match="HTTPS"):
        ChatCompletionsProvider(base_url=url, model="fixture", api_key="", timeout=1)


def test_provider_failure_does_not_surface_response_details():
    provider = ChatCompletionsProvider(
        base_url="http://127.0.0.1:11434/v1", model="fixture", api_key="",
        timeout=1, transport=httpx.MockTransport(lambda _: httpx.Response(401, text="private provider response")),
    )
    with pytest.raises(RuntimeError, match="^Generation provider request failed"):
        provider.generate_json(prompt="Question", system_instruction="Use evidence")


def test_local_ollama_does_not_require_an_api_key():
    provider = get_generation_provider(Settings(_env_file=None, generation_provider="ollama", generation_model="fixture"))
    assert provider.endpoint == "http://127.0.0.1:11434/v1/chat/completions"
    assert "Authorization" not in provider.headers


def test_gemini_provider_reopens_transport_for_each_paper(monkeypatch):
    from unittest.mock import MagicMock, Mock

    clients = [MagicMock(), MagicMock()]
    for i, client in enumerate(clients):
        client.__enter__.return_value.models.generate_content.return_value.text = str(i)
    factory = Mock(side_effect=clients)
    monkeypatch.setattr("app.generation.providers.genai.Client", factory)
    provider = GeminiProvider(api_key="fixture", model="fixture", timeout=1)
    assert provider.generate_json(prompt="Paper one", system_instruction="Use evidence") == "0"
    assert provider.generate_json(prompt="Paper two", system_instruction="Use evidence") == "1"
    assert factory.call_count == 2
