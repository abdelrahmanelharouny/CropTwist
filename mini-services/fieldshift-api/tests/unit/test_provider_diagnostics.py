import asyncio

from app.intelligence.orchestration import provider_diagnostics


class _FakeProvider:
    name = "fake-provider"
    model = "fake-model"
    configured = True

    async def generate(self, messages, **kwargs):
        assert messages[-1]["content"] == "Reply with exactly CROPTWIST_PROVIDER_OK."
        assert kwargs["request_id"] == "croptwist-live-provider-probe"
        assert kwargs["max_tokens"] == provider_diagnostics.PROBE_MAX_OUTPUT_TOKENS
        assert kwargs["max_tokens"] >= 128
        class Result:
            content = "CROPTWIST_PROVIDER_OK"
            model = "fake-model"
        return Result()


def test_live_probe_returns_sanitized_evidence_without_model_output(monkeypatch):
    monkeypatch.setattr(
        provider_diagnostics.provider_registry,
        "get",
        lambda name: _FakeProvider(),
    )
    result = asyncio.run(provider_diagnostics.probe_provider("fake-provider"))
    assert result["status"] == "live_verified"
    assert result["provider"] == "fake-provider"
    assert "content" not in result
    assert "CROPTWIST_PROVIDER_OK" not in str(result)


def test_probe_reports_unregistered_provider(monkeypatch):
    def missing(name):
        raise LookupError(name)
    monkeypatch.setattr(provider_diagnostics.provider_registry, "get", missing)
    assert asyncio.run(provider_diagnostics.probe_provider("missing"))["status"] == "unregistered"


def test_probe_reports_not_configured_without_network(monkeypatch):
    class Disabled:
        name = "disabled"
        model = "model"
        configured = False
    monkeypatch.setattr(provider_diagnostics.provider_registry, "get", lambda name: Disabled())
    assert asyncio.run(provider_diagnostics.probe_provider("disabled"))["status"] == "not_configured"

def test_probe_never_exposes_provider_exception_body(monkeypatch):
    class Broken:
        name = "broken"
        model = "model"
        configured = True

        async def generate(self, messages, **kwargs):
            raise RuntimeError("secret-token-should-never-escape")

    monkeypatch.setattr(provider_diagnostics.provider_registry, "get", lambda name: Broken())
    result = asyncio.run(provider_diagnostics.probe_provider("broken"))
    assert result["status"] == "failed"
    assert "secret-token-should-never-escape" not in str(result)
    assert result["error_category"] == "provider_probe_failed"


def test_probe_reports_registry_none_as_unregistered(monkeypatch):
    monkeypatch.setattr(provider_diagnostics.provider_registry, "get", lambda name: None)
    assert asyncio.run(provider_diagnostics.probe_provider("missing"))["status"] == "unregistered"


def test_probe_uses_a_fresh_message_list_for_each_provider(monkeypatch):
    class MutatingProvider:
        name = "mutating"
        model = "model"
        configured = True

        async def generate(self, messages, **kwargs):
            messages[-1]["content"] = "provider-mutated-this"
            class Result:
                content = "CROPTWIST_PROVIDER_OK"
                model = "model"
            return Result()

    monkeypatch.setattr(
        provider_diagnostics.provider_registry,
        "get",
        lambda name: MutatingProvider(),
    )
    result = asyncio.run(provider_diagnostics.probe_provider("mutating"))
    assert result["status"] == "live_verified"
    assert provider_diagnostics._PROBE_MESSAGES[-1]["content"] == "Reply with exactly CROPTWIST_PROVIDER_OK."


def test_probe_timeout_is_reported_without_raw_exception_details(monkeypatch):
    class Slow:
        name = "slow"
        model = "model"
        configured = True

        async def generate(self, messages, **kwargs):
            await asyncio.sleep(provider_diagnostics.PROBE_TIMEOUT_SECONDS + 0.1)

    monkeypatch.setattr(provider_diagnostics, "PROBE_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(provider_diagnostics.provider_registry, "get", lambda name: Slow())
    result = asyncio.run(provider_diagnostics.probe_provider("slow"))
    assert result["status"] == "failed"
    assert result["error_category"] == "provider_timeout"





def test_probe_timeout_covers_provider_retry_budget():
    from app.intelligence.config import ai_settings

    configured_budget = (
        ai_settings.ai_provider_timeout_seconds * (ai_settings.ai_provider_max_retries + 1)
        + ai_settings.ai_provider_max_backoff_seconds * ai_settings.ai_provider_max_retries
    )
    assert provider_diagnostics.PROBE_TIMEOUT_SECONDS > configured_budget


def test_probe_does_not_verify_an_unexpected_nonempty_response(monkeypatch):
    class WrongResponse:
        name = "wrong-response"
        model = "model"
        configured = True

        async def generate(self, messages, **kwargs):
            class Result:
                content = "I cannot follow the probe instruction."
                model = "model"
            return Result()

    monkeypatch.setattr(provider_diagnostics.provider_registry, "get", lambda name: WrongResponse())
    result = asyncio.run(provider_diagnostics.probe_provider("wrong-response"))
    assert result["status"] == "unexpected_response"
    assert "content" not in result
    assert "I cannot follow" not in str(result)

def test_probe_does_not_echo_untrusted_exception_category(monkeypatch):
    class SecretCategoryError(RuntimeError):
        category = "secret_token_value_123"

    class Broken:
        name = "broken"
        model = "model"
        configured = True

        async def generate(self, messages, **kwargs):
            raise SecretCategoryError("upstream failed")

    monkeypatch.setattr(provider_diagnostics.provider_registry, "get", lambda name: Broken())
    result = asyncio.run(provider_diagnostics.probe_provider("broken"))
    assert result["error_category"] == "provider_probe_failed"
    assert "secret_token_value_123" not in str(result)

def test_probe_handles_non_string_exception_category(monkeypatch):
    class MalformedCategoryError(RuntimeError):
        category = ["not", "a", "string"]

    class Broken:
        name = "broken"
        model = "model"
        configured = True

        async def generate(self, messages, **kwargs):
            raise MalformedCategoryError("upstream failed")

    monkeypatch.setattr(provider_diagnostics.provider_registry, "get", lambda name: Broken())
    result = asyncio.run(provider_diagnostics.probe_provider("broken"))
    assert result["status"] == "failed"
    assert result["error_category"] == "provider_probe_failed"


def test_legacy_bridge_probe_marks_only_fixed_synthetic_prompt_non_sensitive(monkeypatch):
    from app.intelligence import bridge
    from app.intelligence.orchestration.provider import LegacyBridgeProvider

    captured = {}

    async def fake_achat_detail(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return {"content": "CROPTWIST_PROVIDER_OK", "model": "bridge-model"}

    monkeypatch.setattr(bridge, "achat_detail", fake_achat_detail)
    monkeypatch.setattr(
        provider_diagnostics.provider_registry,
        "get",
        lambda name: LegacyBridgeProvider(),
    )
    result = asyncio.run(provider_diagnostics.probe_provider("legacy-llm-bridge"))

    assert result["status"] == "live_verified"
    assert captured["kwargs"]["field_sensitive"] is False
    assert captured["messages"][-1]["content"] == "Reply with exactly CROPTWIST_PROVIDER_OK."


def test_probe_exposes_only_bounded_http_status_for_transient_failure(monkeypatch):
    class TransientFailure(RuntimeError):
        category = "provider_transient_http"
        http_status = 429

    class Broken:
        name = "gemini"
        model = "gemini-test"
        configured = True

        async def generate(self, messages, **kwargs):
            raise TransientFailure("raw response body must never escape")

    monkeypatch.setattr(provider_diagnostics.provider_registry, "get", lambda name: Broken())
    result = asyncio.run(provider_diagnostics.probe_provider("gemini"))
    assert result["status"] == "failed"
    assert result["error_category"] == "provider_transient_http"
    assert result["http_status"] == 429
    assert "raw response body" not in str(result)


def test_probe_omits_invalid_http_status(monkeypatch):
    class MalformedFailure(RuntimeError):
        category = "provider_transient_http"
        http_status = "429 with secret"

    class Broken:
        name = "gemini"
        model = "gemini-test"
        configured = True

        async def generate(self, messages, **kwargs):
            raise MalformedFailure("upstream failed")

    monkeypatch.setattr(provider_diagnostics.provider_registry, "get", lambda name: Broken())
    result = asyncio.run(provider_diagnostics.probe_provider("gemini"))
    assert result["error_category"] == "provider_transient_http"
    assert "http_status" not in result
    assert "secret" not in str(result)

def test_default_provider_chain_excludes_unused_ollama():
    from app.intelligence.config import ai_settings

    assert ai_settings.ollama_enabled is False
    assert ai_settings.provider_order == ("openrouter", "groq", "gemini")
\n

def test_live_probe_budget_allows_reasoning_models_to_finish():
    assert provider_diagnostics.PROBE_MAX_OUTPUT_TOKENS == 128
\n