"""
local_coach.py

Local (hardware-bounded) coaching provider using Ollama's HTTP API.

This version is tuned for smaller local models (e.g., gemma3:4b, qwen3:4b/8b)
and produces structured, citation-backed coaching outputs.

Env vars:
  LOCAL_LLM_URL   (default: http://127.0.0.1:11434)
  LOCAL_LLM_MODEL (default: gemma3:4b)

Ollama endpoint used:
  POST {LOCAL_LLM_URL}/api/chat
"""
from __future__ import annotations

import os
import json
import re
from typing import Any, Dict, List, Optional

import httpx


DEFAULT_LOCAL_URL = "http://127.0.0.1:11434"
DEFAULT_LOCAL_MODEL = "gemma3:4b"


BAD_FAITH_RUBRIC = """Bad-faith / unproductive dialogue behaviors (signal, not verdict):
- strawman: misrepresenting the other person's claim
- moving_goalposts: changing the standard of proof midstream
- ad_hominem: attacking the person instead of the claim
- whataboutism: deflecting to another issue to avoid the point
- gish_gallop: many rapid claims that can't be addressed in time
- loaded_question: embeds an assumption the other must accept
- refuses_evidence: ignores requested evidence or keeps asserting without support
- definition_drift: key terms shift meanings during the conversation
"""


def _render_conversation(turns: List[Dict[str, Any]], max_turns: int = 14) -> str:
    """
    Turns expected as: [{"speaker": "A"|"B", "text": "..."}]
    Keep the context window tight for small local models.
    """
    safe = []
    for t in (turns or [])[-max_turns:]:
        spk = str(t.get("speaker", "")).strip() or "?"
        txt = str(t.get("text", "")).strip().replace("\n", " ")
        if not txt:
            continue
        # keep each line reasonably short
        if len(txt) > 420:
            txt = txt[:420].rstrip() + "…"
        safe.append(f"{spk}: {txt}")
    return "\n".join(safe).strip()


def _build_prompt(topic: str, scope: str, turns: List[Dict[str, Any]], rolling_summary: str = "") -> str:
    convo = _render_conversation(turns)
    rs = (rolling_summary or "").strip()
    rs_block = f"\nRolling summary (if helpful):\n{rs}\n" if rs else ""

    # For small models, be extremely explicit and strict.
    return f"""You are AI Shadow Coach: calm, neutral, fair, concise.
Your job: help keep a live debate productive without taking sides.

TOPIC (anchor):
{topic}

ALLOWED SCOPE (what counts as on-topic):
{scope if scope else "- Use the TOPIC as the scope. Stay on it."}

{rs_block}
TRANSCRIPT (most recent last):
{convo if convo else "[No transcript yet]"}

{BAD_FAITH_RUBRIC}

OUTPUT REQUIREMENTS (IMPORTANT):
- Output MUST be valid JSON ONLY. No markdown, no extra text.
- Every claim you make about behavior/drift MUST include an evidence quote from the transcript (short, exact).
- If you are unsure, keep bad_faith_signals empty and set confidence to "low" when included.
- Keep each string short (<= 25 words where possible).
- Always include Socratic questions.

Return JSON with EXACT keys:
{{
  "socratic_questions": [3 to 6 short Socratic questions],
  "best_next_question": "one question to ask right now",
  "why_this_question": "brief reason (<= 20 words)",
  "bad_faith_signals": [
    {{
      "type": "strawman|moving_goalposts|ad_hominem|whataboutism|gish_gallop|loaded_question|refuses_evidence|definition_drift",
      "confidence": "low|med|high",
      "evidence_quote": "exact short quote from transcript"
    }}
  ],
  "charitable_reframe": "1 sentence restating the other side in good faith (or empty string)",
  "repair_prompt": "one question to restore productive dialogue",
  "on_topic_score": 0-100,
  "drift_reason": "why it drifted, or 'none'",
  "steering_sentence": "one polite but firm sentence to steer back on topic"
}}

Now produce the JSON.
"""


_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _try_parse_json(text: str) -> Dict[str, Any]:
    """
    Best-effort JSON extraction. Small models sometimes prepend/append text.
    """
    text = (text or "").strip()
    if not text:
        return {"error": "Empty model response"}

    # Fast path
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except Exception:
            pass

    # Extract the first JSON object-ish chunk
    m = _JSON_OBJ_RE.search(text)
    if m:
        chunk = m.group(0)
        try:
            return json.loads(chunk)
        except Exception as e:
            return {"error": f"JSON parse failed: {e}", "raw": text[:800]}

    return {"error": "No JSON object found", "raw": text[:800]}


def _normalize(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure keys exist and types are sane so the UI never breaks.
    """
    if not isinstance(obj, dict):
        return {"error": "Model did not return a JSON object"}

    out = dict(obj)

    out.setdefault("socratic_questions", [])
    if not isinstance(out["socratic_questions"], list):
        out["socratic_questions"] = [str(out["socratic_questions"])]

    out.setdefault("best_next_question", "")
    out.setdefault("why_this_question", "")

    out.setdefault("bad_faith_signals", [])
    if not isinstance(out["bad_faith_signals"], list):
        out["bad_faith_signals"] = []

    out.setdefault("charitable_reframe", "")
    out.setdefault("repair_prompt", "")

    # on_topic_score
    score = out.get("on_topic_score", 0)
    try:
        score_i = int(score)
    except Exception:
        score_i = 0
    out["on_topic_score"] = max(0, min(100, score_i))

    out.setdefault("drift_reason", "none")
    out.setdefault("steering_sentence", "")

    return out


def call_local_coach(
    topic: str,
    scope: str,
    turns: List[Dict[str, Any]],
    rolling_summary: str = "",
) -> str:
    """
    Synchronous call used by your FastAPI app.

    Returns: JSON string (normalized) so main.py can json.loads() it safely.
    """
    base_url = os.getenv("LOCAL_LLM_URL", DEFAULT_LOCAL_URL).rstrip("/")
    model = os.getenv("LOCAL_LLM_MODEL", DEFAULT_LOCAL_MODEL)

    prompt = _build_prompt(topic=topic, scope=scope, turns=turns, rolling_summary=rolling_summary)

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        # Keep generation conservative for small models
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
        },
    }

    with httpx.Client(timeout=120) as client:
        r = client.post(f"{base_url}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()

    content = (data.get("message") or {}).get("content", "")
    parsed = _try_parse_json(content)
    normalized = _normalize(parsed)
    return json.dumps(normalized, ensure_ascii=False)
