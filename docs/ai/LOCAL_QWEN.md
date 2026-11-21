# Local Qwen provider

## Purpose and privacy boundary

CropTwist can use a locally running Ollama instance for private field/farmer
context. The default model is
`qwen3:4b-instruct-2507-q4_K_M` (Qwen3-4B-Instruct-2507, Apache-2.0,
approximately 2.5 GB in this quantization). The Ollama library currently
lists manifest digest prefix `0edcdef34593`; record and verify the full digest
on the target host before production rollout.

The provider is **disabled by default**. Enabling it does not download model
weights and does not make the hosted API run Ollama automatically. The API
must be able to reach a local Ollama daemon on the same machine/container
network namespace. The current configuration deliberately accepts loopback
HTTP endpoints only: `localhost`, `127.0.0.1`, or `::1`.

For field-sensitive requests, the provider chain includes Ollama only when
`CROPTWIST_OLLAMA_ENABLED=true`. Hosted providers and the legacy bridge remain
excluded unless the separate `CROPTWIST_AI_ALLOW_FIELD_DATA_TO_PROVIDERS=true`
override is explicitly enabled. With that override off, an Ollama outage must
degrade to deterministic rules; it must not send the prompt to Gemini, Groq or
OpenRouter.

## Local setup

1. Install Ollama on the same host as the API.
2. Pull the pinned quantized model:

   ```bash
   ollama run qwen3:4b-instruct-2507-q4_K_M
   ```

3. Set the following environment variables in the local API environment:

   ```dotenv
   CROPTWIST_LLM_ENABLED=true
   CROPTWIST_OLLAMA_ENABLED=true
   CROPTWIST_OLLAMA_BASE_URL=http://127.0.0.1:11434
   CROPTWIST_OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M
   CROPTWIST_OLLAMA_NUM_CTX=8192
   CROPTWIST_OLLAMA_KEEP_ALIVE=5m
   CROPTWIST_LLM_PROVIDER_ORDER=ollama,gemini,groq,openrouter
   CROPTWIST_AI_ALLOW_FIELD_DATA_TO_PROVIDERS=false
   ```

4. Check Ollama locally with `ollama list` and its local API. Do not expose
   port 11434 to the public internet. Do not place Ollama behind an unauthenticated
   public reverse proxy.
5. Check the provider status endpoint, then perform a separate harmless
   non-sensitive smoke request on the target host. Record the served model,
   latency and token counts. This real-runtime check is manual and is not
   performed by the normal mock-only CI suite.

## Runtime contract

- The adapter uses Ollama's native `POST /api/chat` endpoint.
- Streaming is intentionally disabled in this first adapter; it uses complete
  responses so CropTwist's response validation remains centralized.
- Structured responses pass a JSON Schema through Ollama's `format` field and
  are validated again inside CropTwist.
- The request sets `num_ctx` (default 8192, configurable 2048–16384),
  `num_predict` from the response token budget, and a bounded keep-alive.
- No Authorization header, API key, external embedding or model download is
  required by the adapter.
- Model and usage metadata are normalized into the existing provider contract.

## Acceptance gates before enabling in production

- Install and pin the exact Ollama version and model digest on the target host.
- Verify that the runtime URL is loopback and that port 11434 is not public.
- Run real smoke tests for Modern Standard Arabic, Egyptian Arabic, English,
  evidence citations, JSON-schema conformance and refusal/fallback behavior.
- Benchmark CPU latency, peak RSS, context truncation and concurrent requests
  on the actual deployment hardware.
- Verify that a local-model outage never crosses into hosted providers when
  field-data egress approval is off.
- Record the model tag/digest, Ollama version, context setting and host class
  in deployment provenance.

Mock transport tests verify only the HTTP contract. They do not prove real
inference quality, CPU performance, model loading or privacy of the host
network. No production model claim is made until those acceptance gates pass.

## References

- [Ollama native chat API](https://docs.ollama.com/api/chat)
- [Ollama Qwen3 tags](https://ollama.com/library/qwen3/tags)
- [Qwen3-4B-Instruct-2507 model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
