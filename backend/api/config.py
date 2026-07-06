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

    # --- Provider resilience (chat seam) ---
    # Retry transient (429/5xx/network) failures that occur before the first
    # token, with exponential backoff; a per-endpoint circuit breaker trips after
    # `threshold` consecutive failures and half-opens after the cooldown.
    llm_max_attempts: int = 3
    llm_breaker_threshold: int = 4
    llm_breaker_cooldown_s: float = 30.0
    # When a *workspace* provider fails, fall back to the server-wide provider —
    # but only if the server has a usable key (self-host). A hosted BYO-key
    # instance ships with no fallback key, so this silently no-ops there (each
    # workspace burns its own key; no accidental spend on the operator's key).
    llm_enable_server_fallback: bool = True

    # --- Workspace documents / file grounding ---
    document_max_bytes: int = 8 * 1024 * 1024  # upload cap
    document_max_chars: int = 500_000  # extracted-text cap per document
    # Retrieval at send time: top-k chunks above the relevance floor are folded
    # into the context as quoted data. The floor keeps an unrelated question
    # from dragging the knowledge base into every prompt.
    grounding_k: int = 4
    # Measured on MiniLM: relevant question↔chunk cosines land ~0.24-0.46 even
    # with heavy chunk dilution; unrelated ones sit near (or below) zero. 0.15
    # separates the two with margin on both sides.
    grounding_floor: float = 0.15
    grounding_chunk_chars: int = 1_200
    # Tests set True so ingestion completes within the upload request.
    documents_ingest_inline: bool = False

    # --- Deep Reasoning (Ouroboros) power feature ---
    # Always runs on Groq (its own provider enum — never the chat `llm_provider`,
    # which may be `stub`). Uses `groq_api_key` above.
    #
    # Deliberately decoupled from `groq_model`: chat can stay on a fast/cheap
    # small model while the recursive self-critique loop — whose whole value is
    # reasoning quality — runs on the strongest available model.
    deep_reasoning_model: str = "llama-3.3-70b-versatile"
    deep_reasoning_mode: str = "analyze"  # explore|analyze|create|solve|philosophize
    # Tool policy (FR-14): may deep runs reach out to the web (research fan-out)?
    # Enforced server-side when the graph is built; research additionally needs
    # a TAVILY_API_KEY to do anything at all.
    deep_reasoning_allow_research: bool = True
    deep_reasoning_adaptive: bool = True
    deep_reasoning_compute_budget: int = 4
    deep_reasoning_token_budget: int = 200_000
    # Wall-clock safety cap per deep-run segment, alongside the compute/token
    # budgets. Backoff retries on a rate-limited provider can otherwise stretch a
    # run indefinitely; this halts it cleanly (stop_reason="deadline") with
    # whatever answer has surfaced so far. The normal halt is still convergence.
    deep_reasoning_deadline_s: float = 300.0
    # Deep runs execute server-side (they survive a dropped client); at most this
    # many run concurrently per workspace — the rest queue visibly. Protects the
    # workspace's own provider rate limits (BYO keys burn the workspace's key).
    deep_runs_per_workspace: int = 2
    # How long a finished/paused run's live handle (event log, steer/reconnect
    # surface) is kept in memory. The durable deep_runs row outlives this.
    deep_run_retention_s: float = 30 * 60.0
    # Convergence thresholds. `None` = auto-calibrate to the active embedder at
    # graph-build time (neural MiniLM cosines run much hotter than the lexical
    # fallback's, so one fixed number can't serve both): ~0.90 neural / 0.78
    # lexical. Set explicitly in .env to pin a value.
    deep_reasoning_stability_threshold: float | None = None
    deep_reasoning_confidence_threshold: float = 0.7


settings = Settings()
