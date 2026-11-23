# LLM provider live verification

The ordinary `GET /ai/providers` and operations-status endpoints report
configuration only. They do not make outbound provider calls and therefore
must not claim live connectivity.

## Release-locked provider chain

CropTwist uses exactly **OpenRouter → Groq**. OpenRouter is the primary
provider; Groq is the only fallback. Gemini is deferred and is not registered
as an active provider. Ollama is disabled and is not part of the runtime
registry. The legacy bridge is not part of the active chain.

The runtime rejects any `CROPTWIST_LLM_PROVIDER_ORDER` value other than
`openrouter,groq`. Do not change this setting to experiment with providers.
A different chain requires an explicit architecture decision and a reviewed
code change; do not use environment overrides to switch providers.

To verify the already-selected providers in a controlled environment, run
from `mini-services/fieldshift-api`:

```bash
python scripts/probe_llm_providers.py --provider openrouter --provider groq
```

The probe sends only a fixed non-sensitive test prompt. It never sends a
field, farmer, organization, or knowledge-base record, and it never returns
generated text or raw upstream error bodies.

A result of `not_configured` means that provider credentials are absent; it
does not authorize switching to another provider. A result of
`live_verified` proves only that the selected provider answered the probe at
that time. It does not establish model quality, privacy suitability,
structured-output reliability, or permission to transmit CropTwist field
data. Keep both field-data policy gates disabled unless a separate privacy
review authorizes them.

## Data-egress policy

- `CROPTWIST_AI_ALLOW_FIELD_DATA_TO_PROVIDERS=false`
- `CROPTWIST_OPENROUTER_ALLOW_FIELD_DATA=false`

Hosted-provider probes must use the fixed public/synthetic prompt only.
Farmer records, precise field locations, private farm records, raw
observations, and knowledge-base documents must remain inside CropTwist.

## Failure behavior

The failover chain advances from OpenRouter to Groq only for retryable
transient failures. Authentication, billing, invalid-model/request, policy,
and partial-output failures do not cascade to another provider. Never change
the provider order as a response to a transient failure; inspect the bounded
diagnostic category and let the configured retry/circuit-breaker policy act.
