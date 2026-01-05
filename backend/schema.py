from __future__ import annotations
from typing import Any, Dict, List
import json
import time

REQUIRED_KEYS = ["socratic_question", "bad_faith_signals", "topic_drift", "steer_suggestion"]

def try_parse_json(text: str) -> Dict[str, Any]:
    """
    Best-effort JSON extraction (handles occasional extra text around JSON).
    """
    if text is None:
        raise ValueError("Empty response")
    s = text.strip()

    # direct JSON
    if s.startswith("{") and s.endswith("}"):
        return json.loads(s)

    # try to extract first {...last}
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(s[start:end+1])

    # fallback: treat as socratic question only
    return {
        "socratic_question": s[:500],
        "bad_faith_signals": [],
        "topic_drift": "unknown",
        "steer_suggestion": ""
    }

def normalize_coach_output(obj: Dict[str, Any], provider: str) -> Dict[str, Any]:
    """
    Ensure a stable schema so the UI never depends on provider-specific formatting.
    """
    out: Dict[str, Any] = {}
    out["socratic_question"] = str(obj.get("socratic_question", "")).strip() or "What’s the strongest claim being made, and what evidence would change it?"
    bfs = obj.get("bad_faith_signals", [])
    if isinstance(bfs, str):
        bfs = [bfs]
    out["bad_faith_signals"] = [str(x).strip() for x in bfs if str(x).strip()]
    out["topic_drift"] = str(obj.get("topic_drift", "none")).strip() or "none"
    out["steer_suggestion"] = str(obj.get("steer_suggestion", "")).strip()

    out["_meta"] = {
        "provider": provider,
        "ts": time.time(),
    }
    return out
