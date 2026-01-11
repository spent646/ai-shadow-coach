"""Configuration management for API keys and settings."""

import os
from typing import Optional
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    
    # Get the .env file path relative to this config file
    # config.py is in backend/, .env is in project root
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path, override=True)
except ImportError:
    pass  # python-dotenv not installed, use system environment variables only


class Config:
    """Application configuration from environment variables."""
    
    # Deepgram API key (required for transcription)
    DEEPGRAM_API_KEY: Optional[str] = os.getenv("DEEPGRAM_API_KEY")
    
    # Coach settings
    COACH_TYPE: str = os.getenv("COACH_TYPE", "gemini")  # "ollama" or "gemini"
    
    # Ollama settings (no API key needed, it's local)
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    
    # Gemini settings
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
    
    # Audio engine path
    ENGINE_EXE: str = os.getenv("ENGINE_EXE", "engine/build/Release/audio_engine.exe")
    
    # Periodic reflection settings
    COACH_INTERRUPT_INTERVAL_SECONDS: int = int(os.getenv("COACH_INTERRUPT_INTERVAL_SECONDS", "30"))
    COACH_CONTEXT_WINDOW_MINUTES: int = int(os.getenv("COACH_CONTEXT_WINDOW_MINUTES", "5"))
    
    @classmethod
    def validate(cls) -> list[str]:
        """Validate configuration and return list of missing required settings."""
        missing = []
        
        # Check coach-specific requirements
        if cls.COACH_TYPE == "gemini" and not cls.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY (required when COACH_TYPE=gemini)")
        
        # Deepgram is optional for Phase 1 (transcription not implemented yet)
        # Uncomment when implementing Deepgram:
        # if not cls.DEEPGRAM_API_KEY:
        #     missing.append("DEEPGRAM_API_KEY")
        
        return missing
    
    @classmethod
    def get_deepgram_key(cls) -> Optional[str]:
        """Get Deepgram API key, checking environment and .env file."""
        if cls.DEEPGRAM_API_KEY:
            return cls.DEEPGRAM_API_KEY
        
        # Try loading from .env file if python-dotenv is available
        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                return os.getenv("DEEPGRAM_API_KEY")
        except ImportError:
            pass
        
        return None
