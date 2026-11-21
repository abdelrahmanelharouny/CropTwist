# Local RAG retrieval benchmark

The branch includes an offline evaluator for a small, manually judged corpus.
The corpus is a JSON file containing `documents` with `id/text` and
`queries` with `id/text/relevant_document_ids`. No benchmark data is shipped
because crop-specific relevance judgements must be reviewed by agronomists.

Run after enabling and warming the local adapter:

```bash
python scripts/evaluate_local_embeddings.py ./rag-benchmark.json
```

Metrics include macro Recall@1/3/5, Precision@1/3/5, nDCG@1/3/5 and MRR, with
per-query breakdowns. Keep Arabic and English queries in the same test set and
report both language slices separately in the review. Use the exact same
documents, queries and judgements when comparing MiniLM, BGE-M3 or an
Arabic-English specialist model.

This is a retrieval-quality harness, not a quality result. No model is
production-approved until a reviewed corpus with enough examples across
language, crop, jurisdiction and topic has been evaluated.
