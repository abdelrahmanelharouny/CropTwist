"""Local CPU embeddings for multilingual knowledge retrieval.

Uses a compact multilingual sentence-transformer model supported natively by FastEmbed.
Inference runs locally; no user text is sent to a remote embedding API.
"""
from __future__ import annotations

import asyncio
import math
from functools import lru_cache
from typing import Any

from app.intelligence.config import ai_settings


class FastEmbedMultilingualMiniLMProvider:
    name = "local-fastembed-multilingual-minilm"
    expected_dimensions = 384
    supported_model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, *, threads: int = 2) -> None:
        self._threads = max(1, min(int(threads), 8))
        self.model = ai_settings.ai_knowledge_embedding_model

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_model(model_name: str, cache_dir: str, threads: int) -> Any:
        if model_name != FastEmbedMultilingualMiniLMProvider.supported_model:
            raise RuntimeError("configured local embedding model is not the reviewed multilingual MiniLM model")
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError("FastEmbed is not installed") from exc
        return TextEmbedding(model_name=model_name, cache_dir=cache_dir or None, threads=threads)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not ai_settings.ai_knowledge_embedding_enabled:
            raise RuntimeError("local knowledge embeddings are disabled by configuration")
        if not texts or len(texts) > 32:
            raise ValueError("embedding batch size is outside the supported bound")
        if any(not isinstance(text, str) or not text.strip() or len(text) > 16000 for text in texts):
            raise ValueError("embedding input is outside the supported bound")
        model = self._load_model(self.model, ai_settings.ai_knowledge_embedding_cache_dir, self._threads)
        vectors = model.embed([text.strip() for text in texts])
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
        return await asyncio.to_thread(self._encode, texts)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await asyncio.to_thread(self._encode, [text])
        return vectors[0]


def register_local_embedding_provider(registry: Any) -> None:
    """Register without loading weights or doing network I/O."""
    if ai_settings.ai_knowledge_embedding_enabled:
        registry.register(FastEmbedMultilingualMiniLMProvider())
