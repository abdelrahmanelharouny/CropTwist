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


def test_provider_benchmark_can_require_arabic_and_english_quality_slices():
    class FakeProvider:
        name = "fake"
        model = "fake-model"

        async def embed(self, texts):
            return [[1.0, 0.0] if "wheat" in text else [0.0, 1.0] for text in texts]

        async def embed_query(self, text):
            return [1.0, 0.0] if "قمح" in text or "wheat" in text else [0.0, 1.0]

    result = asyncio.run(evaluate_embedding_provider(
        FakeProvider(),
        documents=[
            {"id": "d1", "text": "wheat cultivation"},
            {"id": "d2", "text": "maize cultivation"},
        ],
        queries=[
            {"id": "ar-1", "text": "زراعة القمح", "relevant_document_ids": ["d1"]},
            {"id": "en-1", "text": "wheat cultivation", "relevant_document_ids": ["d1"]},
        ],
        query_languages={"ar-1": "ar-EG", "en-1": "en-GB"},
    ))
    assert result["language_query_counts"] == {"ar": 1, "en": 1}
    assert result["by_language"]["ar"]["metrics"]["recall@1"] == 1.0
    assert result["by_language"]["en"]["metrics"]["recall@1"] == 1.0


def test_provider_benchmark_fails_closed_when_bilingual_labels_are_incomplete():
    class FakeProvider:
        name = "fake"
        model = "fake-model"

        async def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    with pytest.raises(ValueError, match="missing required language groups: en"):
        asyncio.run(evaluate_embedding_provider(
            FakeProvider(),
            documents=[{"id": "d1", "text": "document"}],
            queries=[{"id": "q1", "text": "query", "relevant_document_ids": ["d1"]}],
            query_languages={"q1": "ar-EG"},
        ))

def test_knowledge_chunk_size_respects_multilingual_model_context():
    from app.intelligence.orchestration.knowledge import chunk_document

    chunks = chunk_document("Crop rotation improves soil health. " * 40)
    assert chunks
    assert max(len(chunk) for chunk in chunks) <= 1200



def test_embedding_eval_cosine_handles_large_finite_vectors_without_overflow():
    from app.intelligence.orchestration.embedding_eval import _cosine

    assert _cosine([1e308, 1e308], [1e308, 1e308]) == pytest.approx(1.0)
    assert _cosine([1e308, 0.0], [0.0, 1e308]) == pytest.approx(0.0)


def test_embedding_eval_cosine_rejects_boolean_components():
    from app.intelligence.orchestration.embedding_eval import _cosine

    with pytest.raises(ValueError, match="non-finite or non-numeric"):
        _cosine([True, 0.0], [1.0, 0.0])



@pytest.mark.parametrize("bad_ks", [(True,), (1.5,), ("1",), (), []])
def test_ranking_metrics_reject_malformed_cutoffs(bad_ks):
    with pytest.raises(ValueError, match="positive integers"):
        evaluate_rankings(
            query_ids=["q"],
            document_ids=["d1"],
            rankings={"q": ["d1"]},
            relevant_document_ids={"q": {"d1"}},
            ks=bad_ks,
        )


def test_ranking_metrics_accept_list_relevance_judgements():
    result = evaluate_rankings(
        query_ids=["q"],
        document_ids=["d1", "d2"],
        rankings={"q": ["d1", "d2"]},
        relevant_document_ids={"q": ["d1"]},
    )
    assert result["metrics"]["recall@1"] == pytest.approx(1.0)


@pytest.mark.parametrize("batch_size", [True, 1.5, "2", 0, 33])
def test_embedding_provider_benchmark_rejects_invalid_batch_size(batch_size):
    class Provider:
        name = "fake"
        model = "fake-model"

    with pytest.raises(ValueError, match="corpus or batch size"):
        asyncio.run(evaluate_embedding_provider(
            Provider(),
            documents=[{"id": "d1", "text": "document"}],
            queries=[{"id": "q1", "text": "query", "relevant_document_ids": ["d1"]}],
            batch_size=batch_size,
        ))


@pytest.mark.parametrize(
    "documents,queries",
    [
        ([{"id": "d1", "text": "doc"}, {"id": "d1", "text": "duplicate"}],
         [{"id": "q1", "text": "query", "relevant_document_ids": ["d1"]}]),
        ([{"id": "d1", "text": "doc"}],
         [{"id": "q1", "text": "query", "relevant_document_ids": ["missing"]}]),
        ([{"id": "", "text": "doc"}],
         [{"id": "q1", "text": "query", "relevant_document_ids": [""]}]),
        ([{"id": "d1", "text": "doc"}],
         [{"id": "q1", "text": "query", "relevant_document_ids": "d1"}]),
    ],
)
def test_embedding_provider_benchmark_rejects_malformed_corpus(documents, queries):
    class Provider:
        name = "fake"
        model = "fake-model"

        async def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    with pytest.raises(ValueError):
        asyncio.run(evaluate_embedding_provider(
            Provider(), documents=documents, queries=queries
        ))


@pytest.mark.parametrize(
    "ranking",
    [
        None,
        ["d1", None],
        ["d1", ["d2"]],
        ["d1", "d1"],
        ["d1", ""],
    ],
)
def test_ranking_metrics_rejects_malformed_ranking_entries(ranking):
    with pytest.raises(ValueError, match="ranking"):
        evaluate_rankings(
            query_ids=["q1"],
            document_ids=["d1", "d2"],
            rankings={"q1": ranking},
            relevant_document_ids={"q1": {"d1"}},
            ks=(1,),
        )
