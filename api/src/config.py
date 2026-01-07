"""Configuration settings for the Brain-OS API."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "brain_os"

    # Ollama
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    ollama_model: str = "llama3.2"

    # Feature flags
    use_mock_clients: bool = True  # Set to False when real services are available

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
