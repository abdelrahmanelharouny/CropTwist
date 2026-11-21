# Local multilingual embedding warmup

The local FastEmbed model is the Qdrant quantized ONNX variant of
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-D,
~50 languages, 512-token truncation, Apache-2.0, approximately 0.22 GB in
FastEmbed 0.7.4). It is loaded lazily and downloaded to the configured cache
on first use. For predictable API latency, run this operator command
from `mini-services/fieldshift-api` after setting
`CROPTWIST_AI_KNOWLEDGE_EMBEDDING_ENABLED=true`:

```bash
python scripts/warmup_local_embeddings.py
```

The script embeds two fixed public test strings (English and Arabic), checks
vector count/dimensions/finiteness, and prints only sanitized metadata. It
does not read any CropTwist knowledge document or field record.

The default cache directory is FastEmbed's own model cache unless
`CROPTWIST_AI_KNOWLEDGE_EMBEDDING_CACHE_DIR` is set. Use persistent disk if the hosting
platform discards container files between restarts; otherwise the model may
need to be downloaded again. Do not enable document/query embedding until the
warmup succeeds and the retrieval benchmark passes.
