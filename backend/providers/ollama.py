from __future__ import annotations
import os
import httpx
from typing import Any, Dict
from schema import try_parse_json, normalize_coach_output
from prompt import build_prompt

DEFAULT_LOCAL_URL = "http://127.0.0.1:11434"
DEFAULT_LOCAL_MODEL = "gemma3:4b"

async def generate(state: Any, *, deep: bool = False) -> Dict[str, Any]:
    base_url = os.getenv("LOCAL_LLM_URL", DEFAULT_LOCAL_URL).rstrip("/")
    model = os.getenv("LOCAL_LLM_MODEL", DEFAULT_LOCAL_MODEL)

    prompt = build_prompt(state, deep=deep)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(f"{base_url}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()

    content = (data.get("message") or {}).get("content", "") or ""
    parsed = try_parse_json(content)
    return normalize_coach_output(parsed, provider="ollama")
