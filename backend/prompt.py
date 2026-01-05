from __future__ import annotations
from typing import Any, List

def build_prompt(state: Any, deep: bool = False) -> str:
    """
    Single prompt builder shared by all providers.
    Keeping it here prevents prompt logic from getting scattered across the codebase.
    """
    topic = getattr(state, "topic", "") or ""
    scope = getattr(state, "scope", "") or ""

    turns = getattr(state, "turns", None) or getattr(state, "history", None) or []
    last_n = turns[-18:] if deep else turns[-10:]
    lines: List[str] = []

    for t in last_n if isinstance(last_n, list) else []:
        speaker = getattr(t, "speaker", None) or getattr(t, "role", None) or "Speaker"
        text = getattr(t, "text", None) or getattr(t, "content", None) or str(t)
        lines.append(f"{speaker}: {text}")

    convo = "\n".join(lines).strip()

    # Keep format tight so small local models behave
    depth_hint = "Be more thorough (but still concise)." if deep else "Be short and actionable."
    return f"""You are AI Shadow Coach: a debate coach for live conversations.

Topic: {topic}
Scope: {scope}

Conversation (most recent last):
{convo}

Task: Provide coaching output in STRICT JSON with exactly these keys:
- socratic_question (string)
- bad_faith_signals (array of short strings)
- topic_drift (string: "none" or brief)
- steer_suggestion (string)

Rules:
- Always include at least 1 Socratic question.
- If uncertain, keep bad_faith_signals empty.
- {depth_hint}
- Output JSON only. No markdown. No extra keys.
"""
