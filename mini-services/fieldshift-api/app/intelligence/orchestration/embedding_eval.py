"""Offline retrieval evaluation for curated Arabic/English RAG benchmarks."""
from __future__ import annotations

import math
from typing import Any


def _cosine(left: list[float], right: list[float]) -> float:
    if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)) or len(left) != len(right) or not left:
        raise ValueError("embedding dimensions do not match")
    try:
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value))
            for value in [*left, *right]
        ):
            raise ValueError("embedding contains non-finite or non-numeric values")
        a = [float(value) for value in left]
        b = [float(value) for value in right]
    except (OverflowError, TypeError, ValueError):
        raise ValueError("embedding contains non-finite or non-numeric values") from None
    # Scale before dot/norm calculations so large but finite vectors cannot
    # overflow their squared norms and silently corrupt benchmark rankings.
    scale_a = max(abs(value) for value in a)
    scale_b = max(abs(value) for value in b)
    if scale_a == 0 or scale_b == 0:
        raise ValueError("zero-norm embedding is not valid for cosine retrieval")
    scaled_a = [value / scale_a for value in a]
    scaled_b = [value / scale_b for value in b]
    norm_a = math.hypot(*scaled_a)
    norm_b = math.hypot(*scaled_b)
    return sum((x / norm_a) * (y / norm_b) for x, y in zip(scaled_a, scaled_b, strict=True))


def evaluate_rankings(
    *,
    query_ids: list[str],
    document_ids: list[str],
    rankings: dict[str, list[str]],
    relevant_document_ids: dict[str, set[str]],
    ks: tuple[int, ...] = (1, 3, 5),
) -> dict[str, Any]:
    """Compute macro Recall@k, Precision@k, nDCG@k and MRR over judged queries."""
    if not query_ids or not document_ids or len(set(query_ids)) != len(query_ids) or len(set(document_ids)) != len(document_ids):
        raise ValueError("benchmark IDs must be non-empty and unique")
    if set(query_ids) - set(relevant_document_ids) or set(query_ids) - set(rankings):
        raise ValueError("every query requires relevance judgements and a ranking")
    if any(not relevant_document_ids[qid] for qid in query_ids):
        raise ValueError("every benchmark query must have at least one relevant document")
    effective_ks = tuple(k for k in ks if 1 <= k <= len(document_ids))
    if not effective_ks:
        raise ValueError("evaluation requires at least one valid k")
    doc_set = set(document_ids)
    metrics: dict[str, float] = {}
    per_query: dict[str, dict[str, float]] = {}
    for qid in query_ids:
        ranking = rankings[qid]
        if len(ranking) != len(document_ids) or set(ranking) != doc_set:
            raise ValueError("each ranking must contain every benchmark document exactly once")
        relevant = relevant_document_ids[qid]
        if not relevant <= doc_set:
            raise ValueError("relevance judgement references an unknown document")
        first_rank = next((rank for rank, doc_id in enumerate(ranking, start=1) if doc_id in relevant), None)
        row = {"mrr": 1.0 / first_rank if first_rank else 0.0}
        for k in effective_ks:
            top = ranking[:k]
            hits = sum(doc_id in relevant for doc_id in top)
            row[f"recall@{k}"] = hits / len(relevant)
            row[f"precision@{k}"] = hits / k
            dcg = sum(1.0 / math.log2(rank + 1) for rank, doc_id in enumerate(top, start=1) if doc_id in relevant)
            ideal_hits = min(len(relevant), k)
            idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
            row[f"ndcg@{k}"] = dcg / idcg if idcg else 0.0
        per_query[qid] = row
    keys = list(next(iter(per_query.values())).keys())
    for key in keys:
        metrics[key] = sum(row[key] for row in per_query.values()) / len(per_query)
    return {"query_count": len(query_ids), "document_count": len(document_ids), "metrics": metrics, "per_query": per_query}


async def evaluate_embedding_provider(
    provider: Any,
    *,
    documents: list[dict[str, str]],
    queries: list[dict[str, Any]],
    batch_size: int = 32,
) -> dict[str, Any]:
    """Embed a curated corpus locally and score its relevance judgements."""
    if not documents or not queries or not 1 <= batch_size <= 32:
        raise ValueError("benchmark corpus or batch size is invalid")
    document_ids = [item["id"] for item in documents]
    query_ids = [item["id"] for item in queries]
    if any(not isinstance(item.get("text"), str) or not item["text"].strip() for item in [*documents, *queries]):
        raise ValueError("benchmark text must be non-empty")
    doc_vectors: list[list[float]] = []
    for offset in range(0, len(documents), batch_size):
        doc_vectors.extend(await provider.embed([item["text"] for item in documents[offset : offset + batch_size]]))
    if len(doc_vectors) != len(documents):
        raise ValueError("embedding provider returned an unexpected document vector count")
    query_vectors: list[list[float]] = []
    query_embedder = getattr(provider, "embed_query", None)
    for query in queries:
        if callable(query_embedder):
            query_vectors.append(await query_embedder(query["text"]))
        else:
            vectors = await provider.embed([query["text"]])
            if len(vectors) != 1:
                raise ValueError("embedding provider returned an unexpected query vector count")
            query_vectors.append(vectors[0])
    rankings: dict[str, list[str]] = {}
    for qid, vector in zip(query_ids, query_vectors, strict=True):
        scored = [(_cosine(vector, doc_vector), doc_id) for doc_id, doc_vector in zip(document_ids, doc_vectors, strict=True)]
        rankings[qid] = [doc_id for _, doc_id in sorted(scored, key=lambda item: (-item[0], item[1]))]
    qrels = {item["id"]: set(item["relevant_document_ids"]) for item in queries}
    result = evaluate_rankings(
        query_ids=query_ids,
        document_ids=document_ids,
        rankings=rankings,
        relevant_document_ids=qrels,
    )
    result["provider"] = provider.name
    result["model"] = provider.model
    return result
