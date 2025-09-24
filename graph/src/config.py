"""
Configuration management for the LangGraph agent.
"""
import os
from typing import Optional

# Try to load dotenv, but don't fail if it's not available (e.g., in production)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, likely in production where env vars are provided directly
    pass

class Config:
    """Application configuration."""
    
    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Duffel API Configuration
    DUFFEL_API_TOKEN: str = os.getenv("DUFFEL_API_TOKEN", "")
    DUFFEL_BASE_URL: str = os.getenv("DUFFEL_BASE_URL", "https://api.duffel.com")
    DUFFEL_API_VERSION: str = os.getenv("DUFFEL_API_VERSION", "v2")
    
    # mem0 Configuration
    MEM0_API_KEY: str = os.getenv("MEM0_API_KEY", "")
    MEM0_NAMESPACE: str = os.getenv("MEM0_NAMESPACE", "bookedai")
    
    # Request Configuration
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        missing = []
        
        if not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
            
        if not cls.DUFFEL_API_TOKEN:
            missing.append("DUFFEL_API_TOKEN")
            
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    @classmethod
    def get_duffel_headers(cls) -> dict:
        """Get headers for Duffel API requests."""
        return {
            "Authorization": f"Bearer {cls.DUFFEL_API_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Duffel-Version": cls.DUFFEL_API_VERSION,
        }


# Global config instance
config = Config() 