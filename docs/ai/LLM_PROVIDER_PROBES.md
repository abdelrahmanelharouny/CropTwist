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
