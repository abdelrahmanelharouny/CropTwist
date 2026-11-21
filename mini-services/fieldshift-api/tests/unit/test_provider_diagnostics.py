import asyncio

from app.intelligence.orchestration import provider_diagnostics


class _FakeProvider:
    name = "fake-provider"
    model = "fake-model"
    configured = True

    async def generate(self, messages, **kwargs):
        assert messages[-1]["content"] == "Reply with exactly CROPTWIST_PROVIDER_OK."
        assert kwargs["request_id"] == "croptwist-live-provider-probe"
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
    assert result["error_category"] == "provider_probe_failed"



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
