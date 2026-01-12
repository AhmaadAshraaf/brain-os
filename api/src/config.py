"""Configuration settings for the Brain-OS API."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8001
    log_level: str = "INFO"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "brain_os_docs"  # Matches your ingest output

    # Ollama
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    ollama_model: str = "llama3.1:8b"

    # Paths (Added to match your .env)
    source_docs_path: str = "/home/ops/brain-os/data/raw"

    # Feature flags
    use_mock_clients: bool = False  # Set to False to use the real Qdrant data

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Logic: Prevents crashes if .env has extra keys


settings = Settings()
