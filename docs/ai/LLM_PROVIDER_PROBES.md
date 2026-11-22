# LLM provider live verification

The ordinary `GET /ai/providers` and operations-status endpoints report
configuration only. They do not make outbound provider calls and therefore
must not claim live connectivity.

To verify credentials in a controlled environment, run from
`mini-services/fieldshift-api`:

```bash
python scripts/probe_llm_providers.py --provider gemini --provider groq --provider openrouter
```

The probe sends only a fixed non-sensitive test prompt, uses a 20-second
timeout, and prints provider/model/status/latency. It never sends a field,
farmer, organization, or knowledge-base record, and it never returns the
generated text or raw upstream error body.

A result of `not_configured` is not a failure. A result of `live_verified`
proves only that the selected provider answered the probe at that time; it
does not establish model quality, privacy suitability, structured-output
reliability, or permission to transmit CropTwist field data. Keep the
field-data policy disabled unless a separate privacy review authorizes it.

## Model default and free-tier privacy

The default Gemini model ID is `gemini-3.8-flash`, the current stable Flash model documented by Google. The Gemini API free tier is $0, but Google states that free-tier content may be used to improve its products. Keep it restricted to public/general or synthetic prompts; never send farmer identities, precise field locations, private farm records or raw field observations through the free-tier route. Paid-tier data handling is different and requires a separate budget and approval. Model ID remains configurable so compatibility can be changed without code edits.

References: [Gemini API pricing and data-use terms](https://ai.google.dev/gemini-api/docs/pricing) · [Gemini API model catalog](https://ai.google.dev/gemini-api/docs/models)

Exit codes: `0` means at least one provider was live-verified and no configured
probe failed; `1` means a configured probe failed or returned an invalid
response; `2` means the command ran but no provider was configured, so no live
connectivity claim can be made.
