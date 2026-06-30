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

    # --- Deep Reasoning (Ouroboros) power feature ---
    # Always runs on Groq (its own provider enum — never the chat `llm_provider`,
    # which may be `stub`). Uses `groq_api_key` above.
    deep_reasoning_mode: str = "analyze"  # explore|analyze|create|solve|philosophize
    deep_reasoning_adaptive: bool = True
    deep_reasoning_compute_budget: int = 4
    deep_reasoning_token_budget: int = 200_000
    # Convergence thresholds, calibrated to the active (lexical-fallback) embedder so
    # an adaptive run halts on a real `converged` signal (the answer has settled)
    # instead of always exhausting the budget. Proven in demo_helix.py. Demo-safe.
    deep_reasoning_stability_threshold: float = 0.78
    deep_reasoning_confidence_threshold: float = 0.7


settings = Settings()
