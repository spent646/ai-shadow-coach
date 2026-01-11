"""Ollama coach with Socratic questioning behavior."""

import requests
import time
from typing import List, Dict
from backend.models import CoachMessage, TranscriptEvent


SOCRATIC_PROMPT = """You are a Socratic coach helping someone reflect on their conversations. Your default behavior is to ask probing questions that:
- Challenge assumptions
- Seek definitions and clarity
- Offer counterexamples
- Identify contradictions
- Encourage deeper thinking

When the user asks a direct question, you can answer it, but still try to include 1-2 Socratic follow-ups.

Default behavior: Return 3-7 Socratic questions per turn, formatted as a numbered list.

Only give direct answers if explicitly requested."""


class Coach:
    """Ollama-based Socratic coach."""
    
    def __init__(self, ollama_url: str = None, model: str = None):
        from backend.config import Config
        self.ollama_url = ollama_url or Config.OLLAMA_URL
        self.model = model or Config.OLLAMA_MODEL
        self.conversation_history: List[CoachMessage] = []
    
    def chat(self, user_message: str, transcript_context: List[TranscriptEvent] = None) -> str:
        """Send message to coach and get response.
        
        Args:
            user_message: User's message
            transcript_context: Recent transcript events for context
        
        Returns:
            Assistant's response text
        """
        # Build context prompt
        context_parts = [SOCRATIC_PROMPT]
        
        if transcript_context:
            context_parts.append("\n\nRecent conversation transcript:")
            for event in transcript_context[-20:]:  # Last 20 events
                context_parts.append(f"[{event.stream}] {event.text}")
        
        context_parts.append(f"\n\nUser question: {user_message}")
        context_parts.append("\n\nRespond with Socratic questions (3-7 questions):")
        
        full_prompt = "\n".join(context_parts)
        
        # Add to conversation history
        self.conversation_history.append(CoachMessage(
            role="user",
            text=user_message,
            ts=time.time()
        ))
        
        # Call Ollama
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False
                },
                timeout=90
            )
            response.raise_for_status()
            result = response.json()
            assistant_text = result.get("response", "I'm having trouble responding right now.")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                assistant_text = f"Error: Model '{self.model}' not found. Please check your OLLAMA_MODEL setting or install the model with: ollama pull {self.model}"
            else:
                assistant_text = f"HTTP Error {e.response.status_code}: {str(e)}"
            print(f"Ollama API error: {e}")
        except requests.exceptions.ConnectionError as e:
            assistant_text = f"Error: Cannot connect to Ollama at {self.ollama_url}. Please ensure Ollama is running."
            print(f"Ollama connection error: {e}")
        except Exception as e:
            assistant_text = f"Error: {str(e)}"
            print(f"Unexpected error calling Ollama: {e}")
        
        # Add to conversation history
        self.conversation_history.append(CoachMessage(
            role="assistant",
            text=assistant_text,
            ts=time.time()
        ))
        
        return assistant_text
    
    def get_history(self) -> List[Dict]:
        """Get conversation history."""
        return [msg.to_dict() for msg in self.conversation_history]
