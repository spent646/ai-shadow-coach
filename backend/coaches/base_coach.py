"""Abstract base class for AI coaches."""

from abc import ABC, abstractmethod
from typing import List, Dict
import time
from backend.models import CoachMessage, TranscriptEvent


# Conversational assistant prompt (default behavior)
SOCRATIC_PROMPT = """You are a helpful AI assistant and conversation coach. Your role is to:
- Answer questions naturally and conversationally
- Provide insights, summaries, and analysis about the conversation transcript
- Help users understand and reflect on their discussions
- Be informative, supportive, and engaging

Default behavior: Have a normal conversation. Answer questions directly, provide helpful analysis, and discuss the transcript naturally.

ONLY use the Socratic method (asking probing questions instead of answering) if the user explicitly requests it (e.g., "use Socratic method", "ask me questions", "challenge my thinking")."""


# Specialized prompt for periodic auto-reflections
REFLECTION_PROMPT = """You are a Socratic coach analyzing a conversation to help participants focus on what matters most.

Analyze the recent conversation transcript and identify:
- The core topic or issue being discussed
- The direction the conversation is heading
- What underlying principle or question is most important

Generate ONE focused Socratic question that:
- Challenges the participants to identify what's most important
- Helps clarify the fundamental issue at stake
- Encourages deeper thinking about priorities and assumptions

Return ONLY the question itself, nothing else. Make it thought-provoking and relevant to the actual content of the conversation."""


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
    
    @abstractmethod
    def generate_reflection(self, transcript_context: List[TranscriptEvent]) -> str:
        """Generate a periodic Socratic reflection question based on recent transcript.
        
        Args:
            transcript_context: Recent transcript events to analyze
        
        Returns:
            A single focused Socratic question
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
        """Build the full prompt including conversational instructions and context.
        
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
        context_parts.append("\n\nRespond naturally and conversationally:")
        
        return "\n".join(context_parts)
    
    def _build_reflection_prompt(self, transcript_context: List[TranscriptEvent]) -> str:
        """Build the prompt for generating periodic reflection questions.
        
        Args:
            transcript_context: Recent transcript events to analyze
            
        Returns:
            Full reflection prompt string
        """
        context_parts = [REFLECTION_PROMPT]
        
        if transcript_context:
            context_parts.append("\n\nRecent conversation transcript (last 5 minutes):")
            for event in transcript_context:
                if event.is_final:  # Only include final transcripts
                    context_parts.append(f"[{event.stream}] {event.text}")
        
        context_parts.append("\n\nGenerate ONE focused Socratic question:")
        
        return "\n".join(context_parts)
