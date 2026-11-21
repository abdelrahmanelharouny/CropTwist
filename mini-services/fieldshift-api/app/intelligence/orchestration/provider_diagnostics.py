"""Opt-in live provider diagnostics using a fixed non-sensitive probe.

A successful configuration check is not a live check. This module performs a
real request only when explicitly called, never sends farm/user data, and never
returns or logs model output or provider exception bodies.
"""
from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

from app.intelligence.orchestration.provider import provider_registry

PROBE_TIMEOUT_SECONDS = 20

_PROBE_MESSAGES = [
    {"role": "system", "content": "You are a connectivity probe. Do not reveal secrets."},
    {"role": "user", "content": "Reply with exactly CROPTWIST_PROVIDER_OK."},
]


async def probe_provider(name: str) -> dict[str, Any]:
    """Probe one registered provider and return sanitized readiness evidence."""
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError("provider name is invalid")
    try:
        provider = provider_registry.get(name.strip())
        if provider is None:
            return {"provider": name.strip(), "status": "unregistered"}
    except LookupError:
        return {"provider": name.strip(), "status": "unregistered"}
    if not provider.configured:
        return {"provider": provider.name, "model": getattr(provider, "model", None), "status": "not_configured"}
    started = perf_counter()
    try:
        result = await asyncio.wait_for(
            provider.generate(
                [dict(message) for message in _PROBE_MESSAGES],
                temperature=0,
                max_tokens=16,
                request_id="croptwist-live-provider-probe",
            ),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        category = getattr(exc, "category", "provider_probe_failed")
        safe_category = category if isinstance(category, str) and category.replace("_", "").isalnum() else "provider_probe_failed"
        return {
            "provider": provider.name,
            "model": getattr(provider, "model", None),
            "status": "failed",
            "error_category": safe_category[:80],
            "latency_ms": max(0, round((perf_counter() - started) * 1000)),
        }
    latency_ms = max(0, round((perf_counter() - started) * 1000))
    if result is None or not isinstance(getattr(result, "content", None), str) or not result.content.strip():
        return {"provider": provider.name, "model": getattr(provider, "model", None), "status": "empty_response", "latency_ms": latency_ms}
    return {
        "provider": provider.name,
        "model": getattr(result, "model", None) or getattr(provider, "model", None),
        "status": "live_verified",
        "latency_ms": latency_ms,
    }
