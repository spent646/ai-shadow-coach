"""Abstract base class for AI coaches."""

from abc import ABC, abstractmethod
from typing import List, Dict
import time
from backend.models import CoachMessage, TranscriptEvent


# Shared Socratic prompting behavior
SOCRATIC_PROMPT = """You are a Socratic coach helping someone reflect on their conversations. Your default behavior is to ask probing questions that:
- Challenge assumptions
- Seek definitions and clarity
- Offer counterexamples
- Identify contradictions
- Encourage deeper thinking

When the user asks a direct question, you can answer it, but still try to include 1-2 Socratic follow-ups.

Default behavior: Return 3-7 Socratic questions per turn, formatted as a numbered list.

Only give direct answers if explicitly requested."""


class BaseCoach(ABC):
    """Abstract base class for all coach implementations."""
    
    def __init__(self):
        """Initialize the coach with empty conversation history."""
        self.conversation_history: List[CoachMessage] = []
    
    @abstractmethod
    def chat(self, user_message: str, transcript_context: List[TranscriptEvent] = None) -> str:
        """Send message to coach and get response.
        
        Args:
            user_message: User's message
            transcript_context: Recent transcript events for context
        
        Returns:
            Assistant's response text
        """
        pass
    
    def get_history(self) -> List[Dict]:
        """Get conversation history.
        
        Returns:
            List of message dictionaries with role, text, and timestamp
        """
        return [msg.to_dict() for msg in self.conversation_history]
    
    def _add_to_history(self, role: str, text: str):
        """Helper method to add a message to conversation history.
        
        Args:
            role: Message role ("user" or "assistant")
            text: Message text
        """
        self.conversation_history.append(CoachMessage(
            role=role,
            text=text,
            ts=time.time()
        ))
    
    def _build_context_prompt(self, user_message: str, transcript_context: List[TranscriptEvent] = None) -> str:
        """Build the full prompt including Socratic instructions and context.
        
        Args:
            user_message: User's message
            transcript_context: Recent transcript events for context
            
        Returns:
            Full prompt string
        """
        context_parts = [SOCRATIC_PROMPT]
        
        if transcript_context:
            context_parts.append("\n\nRecent conversation transcript:")
            for event in transcript_context[-20:]:  # Last 20 events
                context_parts.append(f"[{event.stream}] {event.text}")
        
        context_parts.append(f"\n\nUser question: {user_message}")
        context_parts.append("\n\nRespond with Socratic questions (3-7 questions):")
        
        return "\n".join(context_parts)
