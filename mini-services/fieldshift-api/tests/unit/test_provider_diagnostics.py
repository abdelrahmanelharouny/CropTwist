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
