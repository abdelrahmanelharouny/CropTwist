import asyncio

from app.intelligence import bridge
from app.intelligence.config import ai_settings


def test_async_legacy_bridge_blocks_sensitive_data_before_network(monkeypatch):
    monkeypatch.setattr(ai_settings, "llm_enabled", True)
    monkeypatch.setattr(ai_settings, "ai_allow_field_data_to_providers", False)

    async def forbidden_network(*args, **kwargs):
        raise AssertionError("sensitive prompt must not reach the bridge")

    monkeypatch.setattr(bridge, "_get_async_client", forbidden_network)
    result = asyncio.run(
        bridge.achat_detail([{"role": "user", "content": "private farm record"}])
    )
    assert result is None


def test_sync_legacy_bridge_blocks_sensitive_data_before_network(monkeypatch):
    monkeypatch.setattr(ai_settings, "llm_enabled", True)
    monkeypatch.setattr(ai_settings, "ai_allow_field_data_to_providers", False)

    def forbidden_network(*args, **kwargs):
        raise AssertionError("sensitive prompt must not reach the bridge")

    monkeypatch.setattr(bridge, "_post", forbidden_network)
    assert bridge.chat_detail(
        [{"role": "user", "content": "private farm record"}]
    ) is None
    assert bridge.chat(
        [{"role": "user", "content": "private farm record"}]
    ) is None


def test_explicitly_non_sensitive_legacy_bridge_requests_remain_policy_eligible(monkeypatch):
    monkeypatch.setattr(ai_settings, "ai_allow_field_data_to_providers", False)
    assert bridge._field_data_policy_allows(field_sensitive=False) is True


def test_sensitive_legacy_bridge_requires_explicit_operator_approval(monkeypatch):
    monkeypatch.setattr(ai_settings, "ai_allow_field_data_to_providers", False)
    assert bridge._field_data_policy_allows(field_sensitive=True) is False

    monkeypatch.setattr(ai_settings, "ai_allow_field_data_to_providers", True)
    assert bridge._field_data_policy_allows(field_sensitive=True) is True
