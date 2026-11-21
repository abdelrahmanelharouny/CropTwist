import asyncio
import hashlib

import pytest

from app.intelligence.config import ai_settings
from app.intelligence.orchestration.embedding_adapters import (
    FastEmbedMultilingualE5Provider,
    MODEL_NAME,
    verify_e5_artifact,
)


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


def test_local_e5_document_and_query_embeddings_use_task_prefixes(monkeypatch):
    model = _FakeModel()
    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_enabled", True)
    monkeypatch.setattr(
        FastEmbedMultilingualE5Provider,
        "_load_model",
        staticmethod(lambda model_name, cache_dir, threads: model),
    )
    provider = FastEmbedMultilingualE5Provider()
    documents = asyncio.run(provider.embed(["wheat irrigation"]))
    query = asyncio.run(provider.embed_query("متى أزرع القمح؟"))
    assert len(documents) == 1 and len(documents[0]) == 384
    assert len(query) == 384
    assert documents[0][0] == pytest.approx(0.1)
    assert model.inputs == ["passage: wheat irrigation", "query: متى أزرع القمح؟"]


def test_local_e5_adapter_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_enabled", False)
    provider = FastEmbedMultilingualE5Provider()
    with pytest.raises(RuntimeError, match="disabled by configuration"):
        asyncio.run(provider.embed(["test"]))


def test_local_e5_adapter_rejects_unbounded_batches(monkeypatch):
    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_enabled", True)
    provider = FastEmbedMultilingualE5Provider()
    with pytest.raises(ValueError, match="batch size"):
        asyncio.run(provider.embed(["x"] * 33))


def test_local_e5_adapter_refuses_unreviewed_model(monkeypatch):
    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_enabled", True)
    monkeypatch.setattr(ai_settings, "ai_knowledge_embedding_model", "some/other-model")
    with pytest.raises(RuntimeError, match="not the reviewed multilingual E5 model"):
        asyncio.run(FastEmbedMultilingualE5Provider().embed(["test"]))


def test_e5_artifact_verification_checks_exact_sha256(tmp_path, monkeypatch):
    import app.intelligence.orchestration.embedding_adapters as adapter

    artifact = tmp_path / "onnx"
    artifact.mkdir()
    model_file = artifact / "model.onnx"
    model_file.write_bytes(b"reviewed-model-artifact")
    digest = hashlib.sha256(model_file.read_bytes()).hexdigest()
    monkeypatch.setattr(adapter, "MODEL_SHA256", digest)
    assert verify_e5_artifact(tmp_path) == model_file

    monkeypatch.setattr(adapter, "MODEL_SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="SHA-256"):
        verify_e5_artifact(tmp_path)


def test_fastembed_registry_contains_pinned_e5_custom_model():
    TextEmbedding = FastEmbedMultilingualE5Provider._register_custom_model()
    selected = next(
        model for model in TextEmbedding.list_supported_models()
        if model["model"] == MODEL_NAME
    )
    assert selected["dim"] == 384
    assert selected["license"] == "mit"
    assert selected["model_file"] == "onnx/model.onnx"
