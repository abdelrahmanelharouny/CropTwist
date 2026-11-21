"""Opt-in live provider diagnostics using a fixed non-sensitive probe.

A successful configuration check is not a live check. This module performs a
real request only when explicitly called, never sends farm/user data, and never
returns or logs model output or provider exception bodies.
"""
from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

from app.intelligence.orchestration.provider import ProviderGeneration, provider_registry

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
        async def invoke_probe() -> Any:
            messages = [dict(message) for message in _PROBE_MESSAGES]
            if provider.name == "legacy-llm-bridge":
                # This exact fixed probe is public/non-sensitive. The bridge's
                # normal provider contract correctly defaults to sensitive;
                # diagnostics must explicitly mark this synthetic probe as safe.
                from app.intelligence.bridge import achat_detail

                detail = await achat_detail(
                    messages,
                    temperature=0,
                    max_tokens=16,
                    field_sensitive=False,
                )
                if not isinstance(detail, dict) or not isinstance(detail.get("content"), str):
                    return None
                return ProviderGeneration(
                    content=detail["content"],
                    provider=provider.name,
                    model=detail.get("model") if isinstance(detail.get("model"), str) else None,
                )
            return await provider.generate(
                messages,
                temperature=0,
                max_tokens=16,
                request_id="croptwist-live-provider-probe",
            )

        result = await asyncio.wait_for(invoke_probe(), timeout=PROBE_TIMEOUT_SECONDS)
    except Exception as exc:
        category = getattr(exc, "category", "provider_probe_failed")
        # Never echo arbitrary exception attributes: third-party exceptions may
        # accidentally place credentials or response fragments in category.
        safe_categories = {
            "provider_transient_http", "provider_capacity_limited",
            "provider_credentials_or_permission", "provider_billing_required",
            "provider_invalid_request_or_model", "provider_server_error",
            "provider_http_error", "provider_concurrency_timeout",
            "provider_stream_frame_too_large", "provider_response_too_large",
            "provider_invalid_json_response", "provider_invalid_response_shape",
            "provider_reported_error", "provider_timeout",
            "provider_connection_error", "provider_transport_error",
            "provider_unconfigured", "provider_circuit_open",
            "provider_request_failed", "provider_output_too_large",
            "provider_structured_output_invalid_json",
            "provider_structured_output_schema_mismatch",
            "provider_invalid_stream_frame", "provider_stream_error",
            "provider_stream_incomplete", "provider_stream_interrupted",
            "provider_stream_failed", "provider_cancelled", "provider_safety_block",
            "provider_output_truncated", "provider_incomplete_response",
            "provider_invalid_message_contract", "provider_empty_messages",
            "provider_empty_response", "provider_chain_unavailable",
            "provider_data_policy_blocked", "provider_chain_timeout",
            "provider_schema_unsupported_or_invalid",
        }
        safe_category = category if isinstance(category, str) and category in safe_categories else "provider_probe_failed"
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
    if result.content.strip() != "CROPTWIST_PROVIDER_OK":
        return {
            "provider": provider.name,
            "model": getattr(result, "model", None) or getattr(provider, "model", None),
            "status": "unexpected_response",
            "latency_ms": latency_ms,
        }
    return {
        "provider": provider.name,
        "model": getattr(result, "model", None) or getattr(provider, "model", None),
        "status": "live_verified",
        "latency_ms": latency_ms,
    }
