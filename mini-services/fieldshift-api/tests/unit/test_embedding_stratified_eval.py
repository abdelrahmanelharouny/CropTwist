import pytest

from app.intelligence.orchestration.embedding_eval import evaluate_stratified_rankings


def _benchmark():
    return dict(
        query_ids=["ar-1", "ar-2", "en-1", "en-2"],
        document_ids=["d1", "d2", "d3"],
        rankings={
            "ar-1": ["d1", "d2", "d3"],
            "ar-2": ["d2", "d1", "d3"],
            "en-1": ["d3", "d2", "d1"],
            "en-2": ["d1", "d2", "d3"],
        },
        relevant_document_ids={
            "ar-1": {"d1"},
            "ar-2": {"d1"},
            "en-1": {"d1"},
            "en-2": {"d1"},
        },
        query_languages={
            "ar-1": "ar-EG",
            "ar-2": "ar",
            "en-1": "en-GB",
            "en-2": "en",
        },
    )


def test_stratified_eval_exposes_arabic_and_english_quality_separately():
    result = evaluate_stratified_rankings(**_benchmark())
    assert result["language_query_counts"] == {"ar": 2, "en": 2}
    assert result["by_language"]["ar"]["metrics"]["mrr"] == pytest.approx(0.75)
    assert result["by_language"]["en"]["metrics"]["mrr"] == pytest.approx(2 / 3)
    assert result["overall"]["query_count"] == 4


def test_stratified_eval_fails_closed_when_a_required_language_is_missing():
    data = _benchmark()
    data["query_languages"] = {"ar-1": "ar", "ar-2": "ar", "en-1": "ar", "en-2": "ar"}
    with pytest.raises(ValueError, match="missing required language groups: en"):
        evaluate_stratified_rankings(**data)


def test_stratified_eval_requires_a_language_label_for_every_query():
    data = _benchmark()
    del data["query_languages"]["en-2"]
    with pytest.raises(ValueError, match="every benchmark query requires a language label"):
        evaluate_stratified_rankings(**data)


def test_stratified_eval_rejects_invalid_language_tags():
    data = _benchmark()
    data["query_languages"]["en-2"] = ""
    with pytest.raises(ValueError, match="non-empty BCP-47-like"):
        evaluate_stratified_rankings(**data)
