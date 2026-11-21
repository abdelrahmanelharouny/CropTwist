# Local multilingual E5 embedding warmup

The reviewed local model is `intfloat/multilingual-e5-small` (384-D, MIT).
FastEmbed 0.7.4 loads the ONNX export from a pinned Hugging Face revision
(`ffdcc22`); the 470 MB `onnx/model.onnx` artifact must match SHA-256
`ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665`
before ONNX Runtime is initialized. The wrapper applies the E5 task contract:
`passage: ` for document chunks and `query: ` for user queries.

Run from `mini-services/fieldshift-api` after setting
`CROPTWIST_AI_KNOWLEDGE_EMBEDDING_ENABLED=true`:

```bash
python scripts/warmup_local_embeddings.py
```

The script embeds two fixed public test strings (English and Arabic), checks
vector count/dimensions/finiteness, and prints sanitized metadata only. It
does not read CropTwist knowledge documents or field records.

The default cache directory is FastEmbed's cache unless
`CROPTWIST_AI_KNOWLEDGE_EMBEDDING_CACHE_DIR` is set. Use persistent disk if
the hosting platform discards container files between restarts. Keep semantic
retrieval disabled until warmup and the judged retrieval benchmark pass.
