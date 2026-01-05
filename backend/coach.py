from __future__ import annotations

import os
import time
import asyncio
from typing import Any, Dict, Callable, Awaitable, Optional

from providers import ollama as ollama_provider
from providers import gemini as gemini_provider
from providers import groq as groq_provider

ProviderFn = Callable[..., Awaitable[Dict[str, Any]]]

# Provider registry
PROVIDERS: Dict[str, ProviderFn] = {
    "ollama": ollama_provider.generate,
    "gemini": gemini_provider.generate,
    "groq": groq_provider.generate,
}

# Debounce tracking (in-process)
_last_live_ts: float = 0.0


def _get_provider_name(mode: str) -> str:
    if mode == "deep":
        return os.getenv("COACH_DEEP_PROVIDER", "ollama").strip().lower()
    return os.getenv("COACH_LIVE_PROVIDER", "ollama").strip().lower()


def _debounce_seconds() -> float:
    try:
        return float(os.getenv("COACH_DEBOUNCE_SECONDS", "3.0"))
    except Exception:
        return 3.0


async def run_coach(state: Any, *, mode: str = "live") -> Dict[str, Any]:
    """
    Async coach runner.

    mode:
      - "live": short, frequent coaching (debounced)
      - "deep": on-demand deeper analysis
    """
    global _last_live_ts
    deep = (mode == "deep")

    provider_name = _get_provider_name(mode)
    provider = PROVIDERS.get(provider_name)
    if provider is None:
        raise RuntimeError(
            f"Unknown provider '{provider_name}'. Valid: {', '.join(PROVIDERS.keys())}"
        )

    if not deep:
        now = time.time()
        if (now - _last_live_ts) < _debounce_seconds():
            # Signal to caller to skip updating coach output
            raise RuntimeError("COACH_DEBOUNCED")
        _last_live_ts = now

    # Providers accept (state, deep=bool)
    return await provider(state, deep=deep)


def generate_coach(state: Any, mode: str = "live") -> Optional[Dict[str, Any]]:
    """
    Sync wrapper used by main.py.

    Returns:
      - Dict coach output when a call is made
      - None when debounced (so callers can keep prior coach output)
    """
    try:
        # In FastAPI sync endpoints, this runs in a threadpool with no running loop,
        # so asyncio.run is safe. If a loop exists, schedule safely.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(run_coach(state, mode=mode), loop)
            return fut.result()
        else:
            return asyncio.run(run_coach(state, mode=mode))

    except RuntimeError as e:
        if str(e) == "COACH_DEBOUNCED":
            return None
        raise
