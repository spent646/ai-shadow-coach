from __future__ import annotations
import os
import httpx
from typing import Any, Dict
from schema import normalize_coach_output
from prompt import build_prompt

# Gemini Developer API (AI Studio) REST base
DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"  # safe default; override in env

async def generate(state: Any, *, deep: bool = False) -> Dict[str, Any]:
    """
    Kept 'on hand'—only used when COACH_*_PROVIDER=gemini.
    Uses the Gemini Developer API generateContent endpoint.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to .env when you're ready to enable Gemini.")

    base_url = os.getenv("GEMINI_BASE_URL", DEFAULT_GEMINI_BASE).rstrip("/")
    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()

    prompt = build_prompt(state, deep=deep)

    # Gemini REST: POST /v1beta/models/{model}:generateContent
    url = f"{base_url}/v1beta/models/{model}:generateContent"

    body = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ]
    }

    headers = {
        "Content-Type": "application/json",
        # Recommended auth header for Gemini Developer API
        "x-goog-api-key": api_key,
    }

    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()

    # Extract text
    text = ""
    try:
        cand0 = (data.get("candidates") or [])[0]
        parts = ((cand0.get("content") or {}).get("parts") or [])
        text = "".join([p.get("text", "") for p in parts if isinstance(p, dict)])
    except Exception:
        text = str(data)

    parsed = try_parse_json(text)
    return normalize_coach_output(parsed, provider="gemini")
