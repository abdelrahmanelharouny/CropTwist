"""Pinned local multilingual E5 embeddings for agricultural retrieval.

The 384-D ONNX artifact is downloaded from a pinned Hugging Face revision,
SHA-256 verified, and executed locally through FastEmbed/ONNX Runtime.
E5's task prefixes are part of the embedding contract: documents use
"passage:" and user queries use "query:".
"""
from __future__ import annotations

import asyncio
import hashlib
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.intelligence.config import ai_settings

MODEL_NAME = "intfloat/multilingual-e5-small"
MODEL_REVISION = "919cfbe11fbf4f1b9bb321007c46c14feaf84227"
MODEL_FILE = "onnx/model.onnx"
MODEL_SHA256 = "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665"
MODEL_DIMENSIONS = 384
MODEL_SIZE_GB = 0.47


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_e5_artifact(model_dir: str | Path) -> Path:
    """Require the pinned ONNX bytes before loading any inference session."""
    artifact = Path(model_dir) / MODEL_FILE
    if not artifact.is_file():
        raise RuntimeError("pinned multilingual E5 ONNX artifact is missing")
    if _sha256_file(artifact) != MODEL_SHA256:
        raise RuntimeError("pinned multilingual E5 ONNX artifact failed SHA-256 verification")
    return artifact


class FastEmbedMultilingualE5Provider:
    name = "local-fastembed-multilingual-e5"
    expected_dimensions = MODEL_DIMENSIONS
    supported_model = MODEL_NAME

    def __init__(self, *, threads: int = 2) -> None:
        self._threads = max(1, min(int(threads), 8))
        self.model = ai_settings.ai_knowledge_embedding_model

    @staticmethod
    def _register_custom_model() -> Any:
        try:
            from fastembed import TextEmbedding
            from fastembed.common.model_description import ModelSource, PoolingType
        except ImportError as exc:
            raise RuntimeError("FastEmbed is not installed") from exc

        if not any(
            item.get("model", "").casefold() == MODEL_NAME.casefold()
            for item in TextEmbedding.list_supported_models()
        ):
            TextEmbedding.add_custom_model(
                model=MODEL_NAME,
                pooling=PoolingType.MEAN,
                normalization=True,
                sources=ModelSource(hf="intfloat/multilingual-e5-small"),
                dim=MODEL_DIMENSIONS,
                model_file=MODEL_FILE,
                description="Multilingual E5 small, 384-D, 512-token input, query/passsage prefixes required.",
                license="mit",
                size_in_gb=MODEL_SIZE_GB,
            )
        return TextEmbedding

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_model(model_name: str, cache_dir: str, threads: int) -> Any:
        if model_name != MODEL_NAME:
            raise RuntimeError("configured local embedding model is not the reviewed multilingual E5 model")
        TextEmbedding = FastEmbedMultilingualE5Provider._register_custom_model()
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError("huggingface_hub is required to retrieve the pinned E5 artifact") from exc

        model_dir = snapshot_download(
            repo_id="intfloat/multilingual-e5-small",
            revision=MODEL_REVISION,
            cache_dir=cache_dir or None,
            allow_patterns=[
                "config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
                "onnx/model.onnx",
                "onnx/config.json",
                "onnx/tokenizer.json",
                "onnx/tokenizer_config.json",
                "onnx/special_tokens_map.json",
                "onnx/sentencepiece.bpe.model",
            ],
        )
        verify_e5_artifact(model_dir)
        return TextEmbedding(
            model_name=MODEL_NAME,
            cache_dir=cache_dir or None,
            threads=threads,
            specific_model_path=str(model_dir),
        )

    def _encode(self, texts: list[str], *, prefix: str) -> list[list[float]]:
        if not ai_settings.ai_knowledge_embedding_enabled:
            raise RuntimeError("local knowledge embeddings are disabled by configuration")
        if not texts or len(texts) > 32:
            raise ValueError("embedding batch size is outside the supported bound")
        if any(not isinstance(text, str) or not text.strip() or len(text) > 16000 for text in texts):
            raise ValueError("embedding input is outside the supported bound")
        model = self._load_model(self.model, ai_settings.ai_knowledge_embedding_cache_dir, self._threads)
        vectors = model.embed([f"{prefix}: {text.strip()}" for text in texts])
        result: list[list[float]] = []
        for vector in vectors:
            values = vector.tolist() if hasattr(vector, "tolist") else list(vector)
            vector_values = [float(value) for value in values]
            if len(vector_values) != self.expected_dimensions:
                raise ValueError("embedding model returned an unexpected vector dimension")
            if not all(math.isfinite(value) for value in vector_values):
                raise ValueError("embedding model returned non-finite values")
            if not any(value != 0.0 for value in vector_values):
                raise ValueError("embedding model returned a zero-norm vector")
            result.append(vector_values)
        if len(result) != len(texts):
            raise ValueError("embedding model returned an unexpected vector count")
        return result

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode, texts, prefix="passage")

    async def embed_query(self, text: str) -> list[float]:
        vectors = await asyncio.to_thread(self._encode, [text], prefix="query")
        return vectors[0]


def register_local_embedding_provider(registry: Any) -> None:
    """Register without loading weights or doing network I/O."""
    if ai_settings.ai_knowledge_embedding_enabled:
        registry.register(FastEmbedMultilingualE5Provider())
