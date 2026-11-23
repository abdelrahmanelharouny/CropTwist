"""Run explicit live LLM connectivity probes without sending user data.

Usage (from mini-services/fieldshift-api):
    python scripts/probe_llm_providers.py --provider openrouter --provider groq
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.intelligence.orchestration.provider_diagnostics import probe_provider


async def _run(names: list[str]) -> list[dict[str, object]]:
    # Probe configured vendors concurrently; each call still has its own hard
    # timeout. asyncio.gather preserves the requested output order.
    semaphore = asyncio.Semaphore(3)

    async def bounded(name: str) -> dict[str, object]:
        async with semaphore:
            return await probe_provider(name)

    return list(await asyncio.gather(*(bounded(name) for name in names)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        action="append",
        dest="providers",
        choices=("gemini", "groq", "openrouter", "legacy-llm-bridge"),
        help="Provider to probe. Repeat to probe more than one; default probes configured modern providers.",
    )
    args = parser.parse_args()
    names = args.providers or ["openrouter", "groq"]
    results = asyncio.run(_run(names))
    print(json.dumps(results, indent=2, sort_keys=True))
    if any(item["status"] not in ("live_verified", "not_configured") for item in results):
        return 1
    if not any(item["status"] == "live_verified" for item in results):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
