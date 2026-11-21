"""Mock-only tests for external provider adapters; never call a live vendor."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.intelligence.orchestration.provider import (
    ProviderCapabilities,
    ProviderGeneration,
    ProviderStreamEvent,
)
from app.intelligence.orchestration.provider_adapters import (
    GeminiProvider,
    GroqProvider,
    OllamaProvider,
    OpenRouterProvider,
    ProviderFailoverChain,
    ProviderFailure,
    get_provider_chain,
    get_provider_statuses,
)
from app.intelligence.config import AISettings, ai_settings
from app.intelligence.orchestration import provider_adapters


def _provider_kwargs(transport: httpx.AsyncBaseTransport) -> dict[str, Any]:
    return {
        "api_key": "unit-test-key",
        "model": "unit-test-model",
        "timeout_seconds": 2,
        "connect_timeout_seconds": 1,
        "max_retries": 0,
        "max_concurrent": 1,
        "circuit_threshold": 2,
        "circuit_recovery_seconds": 0.1,
        "max_backoff_seconds": 0,
        "client_factory": lambda timeout: httpx.AsyncClient(transport=transport, timeout=timeout),
    }


def test_gemini_exact_rest_shape_usage_and_request_correlation():
    observed: dict[str, Any] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["headers"] = dict(request.headers)
        observed["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "Grounded answer."}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 31, "candidatesTokenCount": 8, "totalTokenCount": 39},
        })

    provider = GeminiProvider(**_provider_kwargs(httpx.MockTransport(handle)))
    result = asyncio.run(provider.generate(
        [{"role": "system", "content": "rules"}, {"role": "user", "content": "question"}],
        temperature=0.1,
        max_tokens=100,
        request_id="req-1",
    ))
    assert result is not None
    assert result.provider == "gemini"
    assert result.input_tokens == 31 and result.output_tokens == 8
    assert observed["url"].endswith("/unit-test-model:generateContent")
    assert observed["headers"]["x-goog-api-key"] == "unit-test-key"
    assert observed["headers"]["x-client-request-id"] == "req-1"
    assert observed["body"]["systemInstruction"]["parts"][0]["text"] == "rules"
    assert observed["body"]["contents"][0]["role"] == "user"


def test_groq_strict_schema_and_openrouter_required_provider_parameter():
    captured: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "served-model",
            "choices": [{"message": {"content": '{"answer":"ok"}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        })

    schema = {"type": "object", "properties": {
        "answer": {"type": "string"},
        "detail": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
    }}
    transport = httpx.MockTransport(handle)
    groq = GroqProvider(**_provider_kwargs(transport))
    result = asyncio.run(groq.generate_structured(
        [{"role": "user", "content": "return JSON"}], schema=schema, request_id="req-g"
    ))
    assert result is not None and result.model == "served-model"
    strict = captured[-1]["response_format"]["json_schema"]
    assert strict["strict"] is True
    assert strict["schema"]["required"] == ["answer", "detail"]
    assert strict["schema"]["additionalProperties"] is False
    assert strict["schema"]["properties"]["detail"]["required"] == ["ok"]

    router = OpenRouterProvider(**_provider_kwargs(transport))
    asyncio.run(router.generate_structured(
        [{"role": "user", "content": "return JSON"}], schema={"type": "object", "properties": {"answer": {"type": "string"}}}
    ))
    payload = captured[-1]
    assert payload["model"] == "unit-test-model"
    assert payload["provider"] == {"require_parameters": True}
    assert router.capabilities.structured_output_mode == "conditional_provider_parameter_required"


def test_groq_and_openrouter_stream_parsers_retain_tokens_and_usage():
    body = {
        "choices": [{"delta": {"content": "hello"}, "finish_reason": None}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1},
    }
    groq = GroqProvider(**_provider_kwargs(httpx.MockTransport(lambda req: httpx.Response(200))))
    event = groq._parse_stream_event(body)[0]
    assert event.text == "hello" and event.input_tokens == 5 and event.output_tokens == 1

    router = OpenRouterProvider(**_provider_kwargs(httpx.MockTransport(lambda req: httpx.Response(200))))
    usage_frame = router._parse_stream_event({"usage": {"prompt_tokens": 6, "completion_tokens": 2}})
    assert usage_frame[0].text == ""
    assert usage_frame[0].input_tokens == 6
    with pytest.raises(ProviderFailure, match="provider_stream_error"):
        router._parse_stream_event({"choices": [{"delta": {}, "finish_reason": "error"}]})


def test_failover_advances_only_after_retryable_failure():
    class FakeProvider:
        def __init__(self, name: str, outcome: Any):
            self.name = name
            self.model = f"{name}-model"
            self.outcome = outcome
            self.calls = 0
            self.capabilities = ProviderCapabilities(streaming=False)
            self.configured = True

        async def generate(self, messages, **kwargs):
            self.calls += 1
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

        async def generate_structured(self, *args, **kwargs):
            raise AssertionError("not used")

        async def call_tools(self, *args, **kwargs):
            raise AssertionError("not used")

        async def stream(self, *args, **kwargs):
            if False:
                yield ProviderStreamEvent()

    primary = FakeProvider("gemini", ProviderFailure("provider_timeout", True))
    fallback = FakeProvider("groq", ProviderGeneration("answer", "groq", "gpt-oss"))
    chain = ProviderFailoverChain([primary, fallback], allow_sensitive_data=True)
    result = asyncio.run(chain.generate([{"role": "user", "content": "hi"}], request_id="r-1"))
    assert result is not None and result.provider == "groq"
    assert primary.calls == 1 and fallback.calls == 1
    assert result.attempts[-1]["provider"] == "groq"

    blocked = FakeProvider("gemini", ProviderFailure("provider_credentials_or_permission", False))
    never = FakeProvider("groq", ProviderGeneration("should-not-run", "groq"))
    with pytest.raises(ProviderFailure, match="provider_credentials_or_permission"):
        asyncio.run(ProviderFailoverChain([blocked, never], allow_sensitive_data=True).generate([]))
    assert never.calls == 0


def test_failover_never_splices_after_provider_stream_emits_text():
    class StreamingProvider:
        def __init__(self, name: str, *, fails_after_text: bool):
            self.name = name
            self.model = name
            self.fails_after_text = fails_after_text
            self.configured = True
            self.capabilities = ProviderCapabilities(streaming=True)
            self.calls = 0

        async def generate(self, *args, **kwargs):
            raise AssertionError("streaming path expected")

        async def generate_structured(self, *args, **kwargs):
            raise AssertionError("not used")

        async def call_tools(self, *args, **kwargs):
            raise AssertionError("not used")

        async def stream(self, *args, **kwargs):
            self.calls += 1
            yield ProviderStreamEvent(text="partial")
            if self.fails_after_text:
                raise ProviderFailure("provider_stream_interrupted", False, partial_output=True)
            yield ProviderStreamEvent(text=" complete")

    first = StreamingProvider("gemini", fails_after_text=True)
    second = StreamingProvider("groq", fails_after_text=False)
    chain = ProviderFailoverChain([first, second], allow_sensitive_data=True)
    with pytest.raises(ProviderFailure) as caught:
        asyncio.run(chain.generate([{"role": "user", "content": "hi"}], request_id="r-2"))
    assert caught.value.partial_output
    assert first.calls == 1 and second.calls == 0


def test_provider_status_reports_unverified_configuration_without_secrets():
    statuses = get_provider_statuses()
    assert [row["name"] for row in statuses[:4]] == ["ollama", "gemini", "groq", "openrouter"]
    assert statuses[0]["model"] == "qwen3:4b-instruct-2507-q4_K_M"
    assert statuses[0]["status"] == "missing_credentials_or_disabled"
    assert statuses[1]["model"] == "gemini-3.6-flash"
    assert statuses[2]["model"] == "openai/gpt-oss-120b"
    assert statuses[3]["model"] == "nvidia/nemotron-3.5-super-vl:free"
    serialized = json.dumps(statuses)
    assert "unit-test-key" not in serialized
    assert "api_key" not in serialized


def test_legacy_bridge_loopback_is_not_proof_of_local_inference(monkeypatch):
    monkeypatch.setattr(ai_settings, "llm_bridge_url", "http://127.0.0.1:3035")
    monkeypatch.setattr(ai_settings, "ai_allow_field_data_to_providers", False)
    assert provider_adapters._allowed_for_sensitive_data("legacy-llm-bridge") is False

    # The bridge is eligible only after explicit operator approval, regardless
    # of whether its HTTP endpoint is loopback or a remote service.
    monkeypatch.setattr(ai_settings, "ai_allow_field_data_to_providers", True)
    assert provider_adapters._allowed_for_sensitive_data("legacy-llm-bridge") is True


def test_legacy_bridge_sensitive_data_policy_does_not_depend_on_endpoint_host(monkeypatch):
    monkeypatch.setattr(ai_settings, "llm_bridge_url", "http://127.0.0.1:3035")
    monkeypatch.setattr(ai_settings, "ai_allow_field_data_to_providers", False)
    loopback_allowed = provider_adapters._allowed_for_sensitive_data("legacy-llm-bridge")

    monkeypatch.setattr(ai_settings, "llm_bridge_url", "https://bridge.internal.example")
    remote_allowed = provider_adapters._allowed_for_sensitive_data("legacy-llm-bridge")
    assert loopback_allowed is remote_allowed is False


def test_ollama_local_chat_payload_and_usage_are_normalized(monkeypatch):
    observed = {}

    def handle(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["headers"] = dict(request.headers)
        observed["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "qwen3:4b-instruct-2507-q4_K_M",
            "message": {"role": "assistant", "content": "Local answer."},
            "done": True,
            "prompt_eval_count": 23,
            "eval_count": 5,
        })

    monkeypatch.setattr(ai_settings, "llm_enabled", True)
    monkeypatch.setattr(ai_settings, "ollama_enabled", True)
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        num_ctx=8192,
        keep_alive="5m",
        **_provider_kwargs(httpx.MockTransport(handle)),
    )
    result = asyncio.run(provider.generate(
        [{"role": "user", "content": "Explain this synthetic field scenario."}],
        temperature=0,
        max_tokens=128,
        request_id="local-qwen-test",
    ))
    assert result is not None
    assert result.provider == "ollama"
    assert result.input_tokens == 23 and result.output_tokens == 5
    assert observed["url"] == "http://127.0.0.1:11434/api/chat"
    assert "authorization" not in observed["headers"]
    assert observed["body"]["stream"] is False
    assert observed["body"]["options"]["num_ctx"] == 8192
    assert observed["body"]["options"]["num_predict"] == 128
    assert observed["body"]["keep_alive"] == "5m"


def test_ollama_native_json_schema_is_passed_and_validated(monkeypatch):
    captured = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "qwen3:4b-instruct-2507-q4_K_M",
            "message": {"role": "assistant", "content": '{"answer":"grounded"}'},
            "done": True,
            "prompt_eval_count": 12,
            "eval_count": 4,
        })

    monkeypatch.setattr(ai_settings, "llm_enabled", True)
    monkeypatch.setattr(ai_settings, "ollama_enabled", True)
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        num_ctx=8192,
        keep_alive="5m",
        **_provider_kwargs(httpx.MockTransport(handle)),
    )
    schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
    result = asyncio.run(provider.generate_structured(
        [{"role": "user", "content": "Return JSON."}],
        schema=schema,
        temperature=0,
        max_tokens=128,
    ))
    assert result is not None
    assert captured["body"]["format"] == schema
    assert result.content == '{"answer":"grounded"}'


def test_only_enabled_loopback_ollama_is_privacy_eligible(monkeypatch):
    monkeypatch.setattr(ai_settings, "ollama_enabled", True)
    monkeypatch.setattr(ai_settings, "ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(ai_settings, "ai_allow_field_data_to_providers", False)
    assert provider_adapters._allowed_for_sensitive_data("ollama") is True
    assert provider_adapters._allowed_for_sensitive_data("gemini") is False
    assert provider_adapters._allowed_for_sensitive_data("legacy-llm-bridge") is False

    monkeypatch.setattr(ai_settings, "ollama_enabled", False)
    assert provider_adapters._allowed_for_sensitive_data("ollama") is False


def test_ollama_settings_reject_non_loopback_endpoints():
    with pytest.raises(ValidationError, match="loopback"):
        AISettings(ollama_base_url="http://example.com:11434")
    with pytest.raises(ValidationError, match="loopback"):
        AISettings(ollama_base_url="https://127.0.0.1:11434")


def test_sensitive_provider_chain_never_falls_back_to_hosted_models_by_default(monkeypatch):
    class FakeProvider:
        def __init__(self, name):
            self.name = name
            self.model = name
            self.configured = True
            self.capabilities = ProviderCapabilities(streaming=False)

    fake = {name: FakeProvider(name) for name in ("ollama", "gemini", "groq", "openrouter")}
    from app.intelligence.orchestration.provider import provider_registry

    monkeypatch.setattr(provider_registry, "get", lambda name: fake[name])
    monkeypatch.setattr(ai_settings, "llm_enabled", True)
    monkeypatch.setattr(ai_settings, "llm_provider_order", "ollama,gemini,groq,openrouter")
    monkeypatch.setattr(ai_settings, "ollama_enabled", True)
    monkeypatch.setattr(ai_settings, "ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(ai_settings, "ai_allow_field_data_to_providers", False)

    chain = get_provider_chain(field_sensitive=True)
    assert [provider.name for provider in chain.providers] == ["ollama"]
    assert chain.allow_sensitive_data is True


def test_ollama_rejects_non_object_messages_before_request():
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        num_ctx=8192,
        keep_alive="5m",
        **_provider_kwargs(httpx.MockTransport(lambda request: httpx.Response(200, json={}))),
    )
    with pytest.raises(ProviderFailure, match="provider_invalid_message_contract"):
        provider._payload(
            [None],
            temperature=0,
            max_tokens=32,
            schema=None,
            stream=False,
        )


@pytest.mark.parametrize(
    "body,error_category",
    [
        (
            {"message": {"content": "partial"}, "done": False},
            "provider_incomplete_response",
        ),
        (
            {"message": {"content": "truncated"}, "done": True, "done_reason": "length"},
            "provider_output_truncated",
        ),
        (
            {"message": {"content": "missing terminal"}, "done": None},
            "provider_incomplete_response",
        ),
    ],
)
def test_ollama_rejects_incomplete_or_truncated_responses(body, error_category):
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434",
        num_ctx=8192,
        keep_alive="5m",
        **_provider_kwargs(httpx.MockTransport(lambda request: httpx.Response(200, json={}))),
    )
    with pytest.raises(ProviderFailure, match=error_category):
        provider._parse_response(body)
