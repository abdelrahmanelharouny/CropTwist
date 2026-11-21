"""Download/cache the configured local embedding model and verify CPU inference.

Run from mini-services/fieldshift-api before enabling semantic retrieval:
    python scripts/warmup_local_embeddings.py
"""
from __future__ import annotations

import json
import math

from app.intelligence.config import ai_settings
from app.intelligence.orchestration.embedding_adapters import FastEmbedE5Provider


def main() -> int:
    if not ai_settings.ai_knowledge_embedding_enabled:
        raise SystemExit("Set AI_KNOWLEDGE_EMBEDDING_ENABLED=true before warmup.")
    model = FastEmbedE5Provider._load_model(
        ai_settings.ai_knowledge_embedding_model,
        ai_settings.ai_knowledge_embedding_cache_dir,
        2,
    )
    vectors = list(model.embed([
        "Crop rotation improves soil health and reduces pest pressure.",
        "يساعد تدوير المحاصيل على تحسين صحة التربة وتقليل ضغط الآفات.",
    ]))
    if len(vectors) != 2:
        raise SystemExit("Local embedding warmup returned an unexpected vector count.")
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1 or not all(math.isfinite(float(value)) for vector in vectors for value in vector):
        raise SystemExit("Local embedding warmup returned invalid vectors.")
    print(json.dumps({
        "provider": "local-fastembed-e5",
        "model": ai_settings.ai_knowledge_embedding_model,
        "status": "warm",
        "dimensions": dimensions.pop(),
        "sample_count": 2,
        "device": "cpu",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
