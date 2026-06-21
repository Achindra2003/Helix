from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Zero-infra default: a local SQLite file. Prod sets a Postgres URL, e.g.
    #   postgresql+asyncpg://helix:helix@postgres:5432/helix
    database_url: str = "sqlite+aiosqlite:///./helix.db"

    jwt_secret: str = "dev-only-change-me"
    jwt_alg: str = "HS256"
    jwt_ttl_hours: int = 24 * 7

    # Used to build invite links.
    frontend_base_url: str = "http://localhost:5173"

    # LLM provider: stub | groq | ollama
    llm_provider: str = "stub"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"


settings = Settings()
