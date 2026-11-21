import asyncio

import pytest

from app.intelligence.orchestration.embedding_eval import evaluate_embedding_provider, evaluate_rankings


def test_ranking_metrics_are_computed_deterministically():
    result = evaluate_rankings(
        query_ids=["q1", "q2"],
        document_ids=["d1", "d2", "d3"],
        rankings={"q1": ["d1", "d2", "d3"], "q2": ["d3", "d1", "d2"]},
        relevant_document_ids={"q1": {"d1"}, "q2": {"d1"}},
    )
    assert result["metrics"]["mrr"] == pytest.approx(0.75)
    assert result["metrics"]["recall@1"] == pytest.approx(0.5)
    assert result["metrics"]["recall@3"] == pytest.approx(1.0)


def test_ranking_metrics_reject_unjudged_queries():
    with pytest.raises(ValueError, match="at least one relevant"):
        evaluate_rankings(
            query_ids=["q"], document_ids=["d1"],
            rankings={"q": ["d1"]}, relevant_document_ids={"q": set()},
        )


def test_provider_benchmark_uses_query_adapter_when_available():
    class FakeProvider:
        name = "fake"
        model = "fake-model"

        async def embed(self, texts):
            return [[1.0, 0.0] if "wheat" in text else [0.0, 1.0] for text in texts]

        async def embed_query(self, text):
            return [1.0, 0.0] if "قمح" in text else [0.0, 1.0]

    result = asyncio.run(evaluate_embedding_provider(
        FakeProvider(),
        documents=[
            {"id": "d1", "text": "wheat cultivation"},
            {"id": "d2", "text": "maize cultivation"},
        ],
        queries=[{"id": "q1", "text": "زراعة القمح", "relevant_document_ids": ["d1"]}],
    ))
    assert result["metrics"]["recall@1"] == 1.0
    assert result["provider"] == "fake"

def test_knowledge_chunk_size_respects_multilingual_model_context():
    from app.intelligence.orchestration.knowledge import chunk_document

    chunks = chunk_document("Crop rotation improves soil health. " * 40)
    assert chunks
    assert max(len(chunk) for chunk in chunks) <= 400
