import asyncio

import pytest

from app.intelligence.config import ai_settings
from app.intelligence.orchestration.embedding_adapters import FastEmbedMultilingualMiniLMProvider


class _FakeVector:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return self._values


class _FakeModel:
    def __init__(self):
        self.inputs = []

    def embed(self, texts):
        self.inputs.extend(texts)
        return [_FakeVector([0.1, 0.2, 0.3]) for _ in texts]


def test_local_multilingual_document_and_query_embeddings(monkeypatch):
    model = _FakeModel()
    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_enabled", True)
    monkeypatch.setattr(
        FastEmbedMultilingualMiniLMProvider,
        "_load_model",
        staticmethod(lambda model_name, cache_dir, threads: model),
    )
    provider = FastEmbedMultilingualMiniLMProvider()
    documents = asyncio.run(provider.embed(["wheat irrigation"]))
    query = asyncio.run(provider.embed_query("متى أزرع القمح؟"))
    assert documents == [[0.1, 0.2, 0.3]]
    assert query == [0.1, 0.2, 0.3]
    assert model.inputs == ["wheat irrigation", "متى أزرع القمح؟"]


def test_e5_adapter_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_enabled", False)
    provider = FastEmbedMultilingualMiniLMProvider()
    with pytest.raises(RuntimeError, match="disabled by configuration"):
        asyncio.run(provider.embed(["test"]))


def test_e5_adapter_rejects_unbounded_batches(monkeypatch):
    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_enabled", True)
    provider = FastEmbedMultilingualMiniLMProvider()
    with pytest.raises(ValueError, match="batch size"):
        asyncio.run(provider.embed(["x"] * 33))

def test_pinned_fastembed_registry_contains_selected_multilingual_model():
    from fastembed import TextEmbedding

    selected = next(
        model for model in TextEmbedding.list_supported_models()
        if model["model"] == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    assert selected["dim"] == 384
    assert "Multilingual" in selected["description"]
    assert selected["license"] == "apache-2.0"
    assert selected["size_in_GB"] <= 0.25
