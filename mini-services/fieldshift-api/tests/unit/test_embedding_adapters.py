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
        return [_FakeVector([0.1] * 384) for _ in texts]


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
    assert len(documents) == 1 and len(documents[0]) == 384
    assert len(query) == 384
    assert documents[0][0] == pytest.approx(0.1)
    assert model.inputs == ["wheat irrigation", "متى أزرع القمح؟"]


def test_local_minilm_adapter_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_enabled", False)
    provider = FastEmbedMultilingualMiniLMProvider()
    with pytest.raises(RuntimeError, match="disabled by configuration"):
        asyncio.run(provider.embed(["test"]))


def test_local_minilm_adapter_rejects_unbounded_batches(monkeypatch):
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
    assert "512 input tokens" in selected["description"]
    assert selected["license"] == "apache-2.0"
    assert selected["size_in_GB"] <= 0.25


@pytest.mark.parametrize(
    "vector, message",
    [
        ([0.1, 0.2], "dimension"),
        ([float("nan")] * 384, "non-finite"),
        ([0.0] * 384, "zero-norm"),
    ],
)
def test_local_adapter_rejects_invalid_embedding_vectors(monkeypatch, vector, message):
    class BadModel:
        def embed(self, texts):
            return [_FakeVector(vector) for _ in texts]

    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_enabled", True)
    monkeypatch.setattr(
        FastEmbedMultilingualMiniLMProvider,
        "_load_model",
        staticmethod(lambda model_name, cache_dir, threads: BadModel()),
    )
    with pytest.raises(ValueError, match=message):
        asyncio.run(FastEmbedMultilingualMiniLMProvider().embed(["test"]))



def test_local_adapter_refuses_unreviewed_model_before_loading_fastembed(monkeypatch):
    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_enabled", True)
    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_model", "intfloat/multilingual-e5-small")
    provider = FastEmbedMultilingualMiniLMProvider()
    with pytest.raises(RuntimeError, match="not the reviewed multilingual MiniLM model"):
        asyncio.run(provider.embed(["test"]))
