from dataclasses import dataclass, field
from typing import List, Dict, Any
import time

@dataclass
class Turn:
    speaker: str
    text: str
    ts: float = field(default_factory=lambda: time.time())

@dataclass
class SessionState:
    topic: str = "Custom"
    scope: str = ""
    turns: List[Turn] = field(default_factory=list)
    rolling_summary: str = ""
    last_coach: Dict[str, Any] = field(default_factory=dict)

STATE = SessionState()
