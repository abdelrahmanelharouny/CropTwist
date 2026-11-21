"""Evaluate the configured local embedding provider against a judged JSON corpus.

Corpus format:
{
  "documents": [{"id": "doc-1", "text": "..."}],
  "queries": [{"id": "q-1", "text": "...", "relevant_document_ids": ["doc-1"]}]
}
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.intelligence.orchestration.embedding_eval import evaluate_embedding_provider
from app.intelligence.orchestration.knowledge import embedding_provider_registry


async def _evaluate(path: Path) -> dict:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    provider = embedding_provider_registry.get("local-fastembed-multilingual-e5")
    if provider is None:
        raise RuntimeError("Local embedding provider is not registered; enable its setting and restart the API.")
    return await evaluate_embedding_provider(
        provider,
        documents=corpus["documents"],
        queries=corpus["queries"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path, help="JSON file with documents and judged queries")
    args = parser.parse_args()
    result = asyncio.run(_evaluate(args.corpus))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
