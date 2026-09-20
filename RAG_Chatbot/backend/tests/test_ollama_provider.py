"""Focused local-provider tests; no running Ollama process is required."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.rag.context import ContextAssembler
from app.rag.generator import GroundedGenerator
from app.rag.service import RAGService
from app.schemas.rag import ChunkMetadata, DocumentChunk, RetrievedChunk
from app.services.llm import LLMProviderError, OllamaProvider, UnavailableLLMProvider, build_llm_provider


def ollama_settings() -> Settings:
    return Settings(_env_file=None, llm_provider="ollama", ollama_base_url="http://localhost:11434", ollama_model="qwen3:8b")


def client_with(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_provider_configuration_accepts_openrouter_and_ollama_and_rejects_invalid():
    assert Settings(_env_file=None, llm_provider="openrouter").llm_provider == "openrouter"
    assert ollama_settings().llm_provider == "ollama"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_provider="unsupported")


def test_local_ollama_launcher_sets_a_project_relative_backend_pythonpath():
    launcher = Path(__file__).resolve().parents[2] / "scripts" / "run_local_ollama.sh"
    contents = launcher.read_text(encoding="utf-8")
    assert 'export PYTHONPATH="$project_dir/backend${PYTHONPATH:+:$PYTHONPATH}"' in contents
    assert 'exec "$project_dir/.venv/bin/python" -m uvicorn app.main:app' in contents


@pytest.mark.parametrize("provider", ["ollama", "openrouter"])
def test_selected_provider_missing_configuration_is_unavailable_without_fallback(provider):
    settings = Settings(
        _env_file=None,
        llm_provider=provider,
        llm_api_key=None,
        llm_base_url=None,
        llm_model=None,
        ollama_base_url=None,
        ollama_model=None,
    )
    selected = build_llm_provider(settings)
    assert isinstance(selected, UnavailableLLMProvider)
    assert selected.is_ready() is False
    assert "secret" not in selected.reason.lower()
    assert "key" not in selected.reason.lower()


def test_ollama_request_uses_model_json_schema_and_suppresses_thinking():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": '{"answer":"Grounded","evidence_ids":["E1"],"insufficient_evidence":false}', "thinking": "private"}})

    provider = OllamaProvider(ollama_settings(), client=client_with(handler))
    output = provider.generate("system", "question", {"type": "object"})
    assert json.loads(output)["answer"] == "Grounded"
    assert captured["model"] == "qwen3:8b"
    assert captured["stream"] is False and captured["think"] is False
    assert captured["options"] == {"temperature": 0}
    assert captured["format"] == {"type": "object"}


@pytest.mark.parametrize("response", [
    {"message": {}},
    {"message": {"content": ""}},
])
def test_ollama_malformed_or_empty_response_is_safe(response):
    provider = OllamaProvider(ollama_settings(), client=client_with(lambda _: httpx.Response(200, json=response)))
    with pytest.raises(LLMProviderError):
        provider.generate("system", "question")


@pytest.mark.parametrize("exception", [httpx.ConnectError("refused"), httpx.ReadTimeout("timeout")])
def test_ollama_connection_failure_or_timeout_is_safe(exception):
    provider = OllamaProvider(ollama_settings(), client=client_with(lambda _: (_ for _ in ()).throw(exception)))
    with pytest.raises(LLMProviderError):
        provider.generate("system", "question")


def test_ollama_missing_model_is_not_ready():
    provider = OllamaProvider(ollama_settings(), client=client_with(lambda _: httpx.Response(200, json={"models": [{"name": "other:latest"}]})))
    assert provider.is_ready() is False


def test_ollama_non_success_status_is_safe():
    provider = OllamaProvider(ollama_settings(), client=client_with(lambda _: httpx.Response(404, json={"error": "missing"})))
    with pytest.raises(LLMProviderError):
        provider.generate("system", "question")


def test_ollama_output_uses_shared_evidence_validation():
    raw = '{"answer":"Invented","evidence_ids":["E99"],"insufficient_evidence":false}'
    provider = OllamaProvider(ollama_settings(), client=client_with(lambda _: httpx.Response(200, json={"message": {"content": raw}})))
    metadata = ChunkMetadata(document_id="doc", source="XYZ_Policy.pdf", file_path="XYZ_Policy.pdf", page=2, chunk_index=0, content_hash="hash", document_version="version")
    chunk = RetrievedChunk(**DocumentChunk(id="chunk", text="Policy evidence", metadata=metadata).model_dump())

    class Retriever:
        def retrieve(self, question): return [chunk]

    answer = RAGService(Retriever(), ContextAssembler(100), GroundedGenerator(provider)).answer("policy")
    assert "not sure" in answer.answer and answer.sources == []
