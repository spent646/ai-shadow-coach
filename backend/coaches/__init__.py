"""Coach factory for creating different LLM coaches."""

from typing import Optional
from backend.coaches.base_coach import BaseCoach


def create_coach(coach_type: str = "gemini") -> BaseCoach:
    """Factory function to create a coach instance based on type.
    
    Args:
        coach_type: Type of coach to create ("ollama" or "gemini")
    
    Returns:
        BaseCoach instance
        
    Raises:
        ValueError: If coach_type is not supported
    """
    coach_type = coach_type.lower()
    
    if coach_type == "ollama":
        from backend.coaches.ollama_coach import OllamaCoach
        return OllamaCoach()
    elif coach_type == "gemini":
        from backend.coaches.gemini_coach import GeminiCoach
        return GeminiCoach()
    else:
        raise ValueError(
            f"Unsupported coach type: '{coach_type}'. "
            f"Supported types are: 'ollama', 'gemini'"
        )


__all__ = ["create_coach", "BaseCoach"]
