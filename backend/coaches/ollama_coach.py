"""Ollama coach with Socratic questioning behavior."""

import requests
from typing import List
from backend.models import TranscriptEvent
from backend.coaches.base_coach import BaseCoach, SOCRATIC_PROMPT, REFLECTION_PROMPT


class OllamaCoach(BaseCoach):
    """Ollama-based Socratic coach."""
    
    def __init__(self, ollama_url: str = None, model: str = None):
        """Initialize Ollama coach.
        
        Args:
            ollama_url: URL of Ollama server (defaults to Config.OLLAMA_URL)
            model: Model name to use (defaults to Config.OLLAMA_MODEL)
        """
        super().__init__()
        from backend.config import Config
        self.ollama_url = ollama_url or Config.OLLAMA_URL
        self.model = model or Config.OLLAMA_MODEL
    
    def chat(self, user_message: str, transcript_context: List[TranscriptEvent] = None) -> str:
        """Send message to coach and get response.
        
        Args:
            user_message: User's message
            transcript_context: Recent transcript events for context
        
        Returns:
            Assistant's response text
        """
        # Build context prompt using base class helper
        full_prompt = self._build_context_prompt(user_message, transcript_context)
        
        # Add to conversation history
        self._add_to_history("user", user_message)
        
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
        self._add_to_history("assistant", assistant_text)
        
        return assistant_text
    
    def generate_reflection(self, transcript_context: List[TranscriptEvent]) -> str:
        """Generate a periodic Socratic reflection question based on recent transcript.
        
        Args:
            transcript_context: Recent transcript events to analyze
        
        Returns:
            A single focused Socratic question
        """
        # Build reflection prompt using base class helper
        full_prompt = self._build_reflection_prompt(transcript_context)
        
        # Call Ollama
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "stream": False
                },
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            reflection = result.get("response", "").strip()
            
            # Handle empty response
            if not reflection:
                reflection = "What is the core principle you're trying to establish in this discussion?"
                
        except Exception as e:
            print(f"Ollama API error generating reflection: {e}")
            reflection = "What underlying assumption are you both working from in this conversation?"
        
        return reflection