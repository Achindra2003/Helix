import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The placeholder shipped in .env.example and the compose defaults. It is
# public, so any deployment still using it can have its login tokens forged by
# anyone who has read the repository. `assert_secure_config()` refuses to boot
# on it.
PLACEHOLDER_JWT_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    """App configuration, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Zero-infra default: a local SQLite file. Prod sets a Postgres URL, e.g.
    #   postgresql+asyncpg://helix:helix@postgres:5432/helix
    database_url: str = "sqlite+aiosqlite:///./helix.db"

    # Create tables at boot (api/db.py) instead of running migrations. Default
    # True so the self-hosted install stays one command; the hosted instance
    # sets DB_AUTO_CREATE=0 and runs `alembic upgrade head` as a deploy step.
    # Both build the same schema — migrations/env.py explains the split, and
    # the baseline is verified against create_all.
    db_auto_create: bool = True

    # Set when DATABASE_URL points at a transaction-mode connection pooler
    # rather than straight at Postgres — Supabase's port 6543, or any PgBouncer
    # in transaction mode. It disables asyncpg's prepared-statement caching,
    # which such a pooler cannot support. See api/db.py for what breaks without
    # it (an intermittent failure that only appears under concurrency).
    db_pooled: bool = False

    # Give every new account a populated example workspace (api/onboarding.py):
    # a forked thread, a reference edge, a finished deep-run trace, and an
    # ingested document. Static content, so it costs no tokens and works before
    # a provider key is pasted — which is the point, since the features worth
    # seeing are the ones that otherwise need a key.
    seed_example_workspace: bool = True

    # --- Public instance notice -------------------------------------------------
    # Text for the banner a hosted demo shows on every page ("data may be wiped
    # with notice; self-host for keeps"). Empty (the default) means no banner,
    # which is right for a self-hosted install: it is *their* instance and their
    # data, so the warning would be a lie. Served unauthenticated because the
    # login screen has to show it too — keep it to a notice, never anything
    # that would matter to a stranger.
    public_notice: str = ""
    # Where the notice's "self-host" link points. Separate from the text so an
    # operator can retarget it to their own fork without rewriting the sentence.
    public_notice_link: str = "https://github.com/Achindra2003/Helix"

    # --- Crash reporting (api/monitoring.py) ------------------------------------
    # Unset (the default) = no reporting, no SDK, no network client. A
    # self-hoster's errors are theirs, not ours.
    sentry_dsn: str = ""
    sentry_environment: str = "production"
    # Errors are always reported; performance traces are sampled separately and
    # default to off, because tracing on a free tier consumes the quota that
    # error reporting actually needs.
    sentry_traces_sample_rate: float = 0.0

    # --- Transactional email (api/email.py) -------------------------------------
    # Unset = no email sent; the reset link is logged instead, which is what a
    # self-hoster and a local developer both want. Email *verification* is
    # deliberately not implemented: BYO keys mean a fake account cannot spend
    # anything, so it would be friction without safety.
    resend_api_key: str = ""
    # Must be an address on a domain verified in your Resend account, or Resend
    # rejects the send.
    email_from: str = "Helix <onboarding@resend.dev>"
    # Short by design: a reset link is a bearer credential sitting in an inbox.
    # Long enough to survive slow mail delivery, short enough that a forwarded
    # or leaked message goes stale quickly. Completing a reset invalidates the
    # link immediately regardless (see security.make_reset_token).
    password_reset_ttl_minutes: int = 30

    jwt_secret: str = PLACEHOLDER_JWT_SECRET
    jwt_alg: str = "HS256"
    jwt_ttl_hours: int = 24 * 7

    # Escape hatch for local development, where the placeholder secret is
    # harmless and typing a real one every time is friction. Opt-in and
    # explicit: HELIX_DEV=1. Never set it on anything reachable from a network.
    helix_dev: bool = False

    # Where to persist an auto-generated signing secret when JWT_SECRET is not
    # set. Empty (the default) means "no fallback — refuse to boot", which is
    # right for a bare-metal deploy where an unexpected file is a surprise. The
    # container sets this to a path on its data volume so `docker compose up`
    # stays a single command and still gets a unique secret per install.
    jwt_secret_file: str = ""

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

    # --- Abuse caps (P2) ---
    # Modest ceilings, not business rules: they exist so one account cannot
    # fill the database or wedge a workspace, and every one is far above what
    # honest use of a team workspace reaches. Set any of them to 0 to disable
    # that cap entirely (useful for a trusted single-tenant self-host).
    max_workspaces_per_user: int = 20
    max_members_per_workspace: int = 50
    # How many times one invite link may be redeemed. Expiry already existed;
    # without a use cap a leaked link is an open door until it expires.
    invite_max_uses: int = 25
    # Request body ceilings, enforced by middleware (see api/main.py). The
    # global cap sits above document_max_bytes so uploads still fit; the
    # message cap is much tighter because a prompt is text, and an enormous one
    # is either abuse or a bug.
    max_request_bytes: int = 12 * 1024 * 1024
    max_message_bytes: int = 64 * 1024

    # --- Rate limits (P2; see api/rate_limit.py) ---
    # Sliding windows per user (or per IP when unauthenticated). The threat is
    # database spam and run floods, not token theft — BYO keys mean a flood
    # burns the workspace's own provider quota. Any limit set to 0 is disabled;
    # rate_limit_enabled=False turns the whole mechanism off.
    rate_limit_enabled: bool = True
    # Registration and login share this one: it guards both mass-signup and
    # password guessing, neither of which carries a token, so both key on IP.
    rate_limit_auth_per_hour: int = 20
    # Ordinary chat. Well above human typing speed, low enough that a script
    # cannot fill the node table.
    rate_limit_messages_per_minute: int = 30
    # Deep and agent runs: each fans out into many model and tool calls, so
    # they get a tighter budget than plain messages.
    rate_limit_runs_per_minute: int = 10
    # Document uploads: the heaviest write path (a file up to
    # document_max_bytes, then a chunk row per ~220 words and an embedding per
    # chunk). Requires membership, so this bounds a member rather than the open
    # internet — hence per-hour, and set generously enough that a real bulk
    # import of a reference folder still goes through in one sitting.
    rate_limit_uploads_per_hour: int = 120

    # --- Workspace documents / file grounding ---
    document_max_bytes: int = 8 * 1024 * 1024  # upload cap
    document_max_chars: int = 500_000  # extracted-text cap per document
    # Retrieval at send time: top-k chunks above the relevance floor are folded
    # into the context as quoted data. The floor keeps an unrelated question
    # from dragging the knowledge base into every prompt.
    grounding_k: int = 4
    # Measured on MiniLM against the golden retrieval set (evals/retrieval.py):
    # every positive query's relevant document scores ≥ 0.24; the strongest
    # unrelated query tops out at 0.18 (money/office vocabulary brushing the
    # pricing sheet). 0.20 splits them with margin on both sides — the original
    # 0.15 leaked two negatives, which is exactly what the harness is for.
    grounding_floor: float = 0.20
    grounding_chunk_chars: int = 1_200
    # Retrieval arms: hybrid (dense + BM25 fused by RRF, the default) | dense |
    # lexical. Kept switchable so the eval harness (evals/retrieval.py) can
    # measure each arm alone — thresholds below come from its report.
    grounding_retrieval_mode: str = "hybrid"
    # Lexical relevance floor in squashed-BM25 units (score s -> s/(s+5); 0.30
    # ≈ raw BM25 ~2.1, i.e. one genuinely rare term). Admits exact-identifier
    # matches dense misses, while common-word overlap from unrelated questions
    # stays below it — measured on the golden set (evals/retrieval.py).
    grounding_lexical_floor: float = 0.30
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

    # --- Agent tool loop (FR-14; see api/tools/) ---
    # Web search runs on Tavily. Without a key the tool is *visibly
    # unavailable* in the catalog and never offered to the model — same key
    # the deep-reasoning research detour uses.
    tavily_api_key: str = ""
    # One round = the model requests tools, they run, it reads the results.
    # Bounds the loop so a model that keeps asking for "one more search"
    # terminates; the graph's recursion limit is derived from this.
    agent_max_tool_rounds: int = 5

    # --- Observability (OTel GenAI tracing; see api/telemetry.py) ---
    # Unset (the default) = no SDK installed, no-op tracer, nothing exported —
    # the hermetic suite and zero-infra self-host stay untouched. Point it at
    # any OTLP/HTTP backend; for a self-hosted Langfuse:
    #   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:3000/api/public/otel
    #   OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic <base64(pk:sk)>
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_headers: str = ""
    otel_service_name: str = "helix-api"


settings = Settings()


class InsecureConfigError(RuntimeError):
    """Raised at startup when the configuration is unsafe to expose."""


def _generate_secret() -> str:
    return secrets.token_urlsafe(32)


def secure_jwt_secret(cfg: Settings | None = None) -> str:
    """Resolve a safe token-signing secret, or refuse to start.

    The placeholder is printed in this repository, so any instance still using
    it can have a session forged for any user by anyone who has read the code.
    A warning is not enough — self-hosters do not read logs, and the instance
    would run that way forever.

    But a hard failure alone would break the one-command install, so the
    resolution order below keeps *both* properties (secure by default, and
    `docker compose up` still just works):

    1. An explicitly configured JWT_SECRET always wins.
    2. Otherwise, if a secret file is configured (the container sets
       JWT_SECRET_FILE=/data/.jwt_secret on its data volume), read it — or
       generate one, persist it 0600, and log that it happened. Persisting is
       what makes it survive restarts; a secret regenerated on every boot would
       log the whole team out on every restart.
    3. Otherwise refuse to boot, with a ready-to-paste secret in the message.

    HELIX_DEV=1 opts out entirely, for local development where the placeholder
    is harmless.

    Called from the app's lifespan rather than at import time: importing the
    settings module must stay free of side effects like writing files.
    """
    cfg = cfg or settings

    # An empty or whitespace-only value counts as unset, not as a secret.
    # `JWT_SECRET: ${JWT_SECRET:-}` in compose produces exactly that when the
    # operator has not set one, and signing tokens with "" would be strictly
    # worse than the placeholder.
    configured = (cfg.jwt_secret or "").strip()

    if configured and configured != PLACEHOLDER_JWT_SECRET:
        return configured
    if cfg.helix_dev:
        return cfg.jwt_secret

    if cfg.jwt_secret_file:
        path = Path(cfg.jwt_secret_file)
        try:
            if path.is_file():
                existing = path.read_text(encoding="utf-8").strip()
                if existing:
                    return existing
            path.parent.mkdir(parents=True, exist_ok=True)
            generated = _generate_secret()
            # 0600 before writing: never briefly world-readable on disk.
            path.touch(mode=0o600, exist_ok=True)
            path.chmod(0o600)
            path.write_text(generated, encoding="utf-8")
            print(
                f"[helix] No JWT_SECRET set. Generated one and stored it at "
                f"{path}. It persists across restarts; delete the file to "
                f"rotate (this logs everyone out).",
                flush=True,
            )
            return generated
        except OSError as exc:
            raise InsecureConfigError(
                f"\n  Refusing to start: JWT_SECRET is unset and the secret file"
                f"\n  {path} could not be read or written ({exc}).\n"
                f"\n  Set JWT_SECRET explicitly:\n"
                f"\n      JWT_SECRET={_generate_secret()}\n"
            ) from exc

    raise InsecureConfigError(
        "\n"
        "  Refusing to start: JWT_SECRET is still the public placeholder.\n"
        "\n"
        "  It signs every login token. Anyone who has seen this repository can\n"
        "  forge a session for any user on this instance.\n"
        "\n"
        "  Set it to the freshly generated value below (or any random string):\n"
        "\n"
        f"      JWT_SECRET={_generate_secret()}\n"
        "\n"
        "  Changing it later logs everyone out and invalidates saved workspace\n"
        "  provider keys (their encryption is derived from it), so set it\n"
        "  before inviting anyone.\n"
        "\n"
        "  Alternatively set JWT_SECRET_FILE to a writable path and one will be\n"
        "  generated and persisted there (this is what the container does).\n"
        "\n"
        "  For local development only, skip this check with HELIX_DEV=1.\n"
    )
