from __future__ import annotations
import os
from typing import Any, Dict
from schema import normalize_coach_output
from prompt import build_prompt


async def generate(state: Any, *, deep: bool = False) -> Dict[str, Any]:
    """
    Placeholder adapter.

    If you still want Groq as an optional provider, move your existing Groq call
    into here (so the rest of the app never calls Groq directly).
    """
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set.")

    raise RuntimeError("Groq provider adapter not wired yet. Paste your Groq implementation into providers/groq.py.")
