import asyncio

from scripts import probe_llm_providers


def test_cli_probes_multiple_providers_concurrently_and_preserves_order(monkeypatch):
    active = 0
    maximum_active = 0

    async def fake_probe(name):
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"provider": name, "status": "live_verified"}

    monkeypatch.setattr(probe_llm_providers, "probe_provider", fake_probe)
    results = asyncio.run(probe_llm_providers._run(["gemini", "groq", "openrouter"]))

    assert maximum_active == 3
    assert [item["provider"] for item in results] == ["gemini", "groq", "openrouter"]
