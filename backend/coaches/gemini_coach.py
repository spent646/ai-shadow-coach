"""Gemini coach with Socratic questioning behavior."""

from typing import List
from backend.models import TranscriptEvent
from backend.coaches.base_coach import BaseCoach, SOCRATIC_PROMPT, REFLECTION_PROMPT


class GeminiCoach(BaseCoach):
    """Google Gemini-based Socratic coach."""
    
    def __init__(self, api_key: str = None, model: str = None):
        """Initialize Gemini coach.
        
        Args:
            api_key: Gemini API key (defaults to Config.GEMINI_API_KEY)
            model: Model name to use (defaults to Config.GEMINI_MODEL)
        """
        super().__init__()
        from backend.config import Config
        
        self.api_key = api_key or Config.GEMINI_API_KEY
        self.model_name = model or Config.GEMINI_MODEL
        
        # Validate API key
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is required. Please set it in your .env file or environment variables. "
                "Get your API key from: https://makersuite.google.com/app/apikey"
            )
        
        # Configure Gemini
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
            self.genai = genai
        except ImportError:
            raise ImportError(
                "google-generativeai library is required for Gemini coach. "
                "Install it with: pip install google-generativeai"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Gemini: {str(e)}")
    
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
        
        # Call Gemini API
        try:
            # Use streaming for faster responses
            response = self.model.generate_content(
                full_prompt,
                stream=True,
                generation_config={
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 2048,
                }
            )
            
            # Collect streamed response
            assistant_text = ""
            for chunk in response:
                if chunk.text:
                    assistant_text += chunk.text
            
            # Handle empty response
            if not assistant_text.strip():
                assistant_text = "I'm having trouble responding right now. Could you rephrase your question?"
                
        except self.genai.types.BlockedPromptException as e:
            assistant_text = "I cannot respond to that prompt due to safety filters. Please try rephrasing your question."
            print(f"Gemini blocked prompt: {e}")
        except self.genai.types.StopCandidateException as e:
            assistant_text = "My response was incomplete due to safety filters. Please try a different question."
            print(f"Gemini stopped generation: {e}")
        except Exception as e:
            error_msg = str(e).lower()
            
            # Handle specific error types
            if "api key" in error_msg or "unauthorized" in error_msg or "403" in error_msg:
                assistant_text = (
                    "Error: Invalid or missing API key. Please check your GEMINI_API_KEY setting. "
                    "Get your API key from: https://makersuite.google.com/app/apikey"
                )
            elif "quota" in error_msg or "rate limit" in error_msg or "429" in error_msg:
                assistant_text = (
                    "Error: Rate limit exceeded. Please wait a moment and try again, "
                    "or check your API quota at: https://console.cloud.google.com/"
                )
            elif "model" in error_msg and "not found" in error_msg:
                assistant_text = (
                    f"Error: Model '{self.model_name}' not found. "
                    f"Please check your GEMINI_MODEL setting."
                )
            elif "network" in error_msg or "connection" in error_msg:
                assistant_text = (
                    "Error: Network connection failed. Please check your internet connection and try again."
                )
            else:
                assistant_text = f"Error: {str(e)}"
            
            print(f"Gemini API error: {e}")
        
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
        
        # Call Gemini API
        try:
            response = self.model.generate_content(
                full_prompt,
                generation_config={
                    "temperature": 0.8,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 200,
                }
            )
            
            reflection = response.text.strip()
            
            # Handle empty response
            if not reflection:
                reflection = "What is the core principle you're trying to establish in this discussion?"
                
        except Exception as e:
            print(f"Gemini API error generating reflection: {e}")
            reflection = "What underlying assumption are you both working from in this conversation?"
        
        return reflection