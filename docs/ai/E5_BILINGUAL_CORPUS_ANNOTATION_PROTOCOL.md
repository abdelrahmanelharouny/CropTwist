# E5 Arabic/English retrieval corpus: annotation and acceptance protocol

**Model:** `intfloat/multilingual-e5-small`, 384 dimensions. Query text must use the `query: ` prefix and document text the `passage: ` prefix.  
**Status:** benchmark harness exists; reviewed judgments and an accepted score report do not. The corpus below defines the work; it does not manufacture relevance labels.

## Corpus design

Create a source-grounded corpus of Egyptian agriculture and CropTwist knowledge, not generic web snippets. Include:
- Egyptian Arabic (colloquial), Modern Standard Arabic and English
- crop calendars and season definitions; crop identification and classification legends; irrigation/water requirements; soil properties; satellite product interpretation; pests/disease only where a reviewed source exists; regulations and official statistics
- Egypt-wide and governorate/region-specific evidence, with explicit applicability dates
- both answerable and unanswerable queries, including spelling variation, transliteration, Arabic morphology, mixed Arabic/English technical terms and ambiguous crop names

## Minimum annotation targets

- At least 300 judged queries: 150 Arabic and 150 English; target 500 source passages across at least 5 evidence categories.
- At least 30 queries per language/category where the category is applicable; record categories that genuinely have no Egyptian source rather than filling them with guesses.
- Every query must have at least one gold passage for answerable cases. Unanswerable queries must explicitly carry `answerable=false` and a reviewer rationale; do not encode them as an empty relevance list in the current evaluator until its schema is extended.
- Two independent reviewers label relevance; a third reviewer adjudicates disagreements. Numeric agronomic claims require an agronomist or a qualified domain reviewer.
- Split train/dev/test by source document and publisher, not random query rows, to prevent near-duplicate passage leakage.

## Required document metadata

`id`, `text`, `language`, `source_id`, `publisher`, `title`, `source_url`, `publication_date`, `retrieved_at`, `geography`, `crop_codes`, `season`, `evidence_category`, `license_name`, `license_url`, `commercial_use_allowed`, `review_status`, `reviewer_id`, `source_version`, `passage_hash`.

## Required query and judgment metadata

`id`, `text`, `language`, `intent`, `geography`, `crop_code`, `season`, `answerable`, `relevant_document_ids`, `reviewer_ids`, `adjudication_status`, `difficulty`, `notes`.

## Scoring and release gate

Run `scripts/evaluate_local_embeddings.py` against the same frozen documents and judgments for each model. Publish per-language and overall:
- Recall@5 and Recall@10 (mandatory), Precision@5/@10, MRR and nDCG@5/@10
- query count and source/category/geography coverage
- bootstrap 95% confidence intervals by query (and by source cluster as a sensitivity analysis)
- failure examples and language-specific gaps
- model revision, tokenizer revision, embedding dimension, normalization, retrieval metric, corpus commit/hash, software versions and hardware
- latency, peak RSS and throughput as operational metrics, separate from retrieval quality

Do not enable semantic retrieval in production until Arabic and English each meet the release threshold agreed by the project owner and domain reviewer. A good aggregate score cannot hide a weak language slice. BGE-M3 may be compared only on the identical corpus, judgments, hardware and retrieval settings.

## Annotation file template

Use the existing evaluator's JSON structure for judged, answerable queries. Keep review metadata in an adjacent manifest so the current evaluator remains backward compatible. The initial corpus must be populated from licensed, versioned sources and reviewed by humans; do not generate pseudo-gold judgments with an LLM.
