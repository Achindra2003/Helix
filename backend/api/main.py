from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import db, rate_limit, telemetry
from .config import secure_jwt_secret, settings
from .conversation.map import router as map_router
from .conversation.router import router as conversation_router
from .documents.router import router as documents_router
from .prompts.router import router as prompts_router
from .realtime import router as realtime_router
from .routers import auth, workspaces


@asynccontextmanager
async def lifespan(app: FastAPI):
    # First, before anything else starts: resolve a safe token-signing secret,
    # or refuse to run. Raising here means the process never listens.
    # Assigned back onto `settings` because security.py and provider_settings.py
    # read `settings.jwt_secret` at call time.
    settings.jwt_secret = secure_jwt_secret()
    telemetry.init_telemetry()  # no-op unless an OTLP endpoint is configured
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(title="Helix API", version="0.1.0", lifespan=lifespan)

# Dev CORS: allow the Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_base_url],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request size caps (P2) --------------------------------------------------
# Enforced here rather than per-route so nothing can be added later that
# forgets them, and so an oversized body is rejected before any handler,
# database session, or model call is entered.
#
# Two tiers: prompt-carrying routes get a tight text-sized cap, everything else
# gets a global ceiling that still admits document uploads
# (settings.document_max_bytes, 8 MB by default).
_PROMPT_PATH_MARKERS = ("/messages", "/deep", "/agent", "/steer", "/from-prompt")


def _body_limit_for(path: str) -> int:
    """The cap that applies to a path, in bytes."""
    if path.startswith("/conversations") and any(
        marker in path for marker in _PROMPT_PATH_MARKERS
    ):
        return settings.max_message_bytes
    return settings.max_request_bytes


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    """Reject oversized bodies up front, by Content-Length.

    Trusting the declared length is deliberate: it is what lets the request be
    refused *before* the body is read, which is the whole point — streaming
    gigabytes into memory to then reject them is the attack, not the defence.
    A client that lies about the length still cannot exceed the server's own
    body handling, and uvicorn caps what it will buffer.

    Note this is a byte cap, not a character count: a prompt of multi-byte
    characters hits it sooner than an ASCII one. That is the correct thing to
    bound here, since bytes are what cost storage and bandwidth.
    """
    limit = _body_limit_for(request.url.path)
    if limit > 0:
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                size = int(declared)
            except ValueError:
                size = 0
            if size > limit:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "payload_too_large",
                            "message": (
                                f"Request body is {size} bytes; the limit for "
                                f"this endpoint is {limit}."
                            ),
                        }
                    },
                )
    return await call_next(request)


@app.middleware("http")
async def enforce_rate_limits(request: Request, call_next):
    """Throttle account creation, logins, messages, and runs (P2).

    Registered after the size cap (middleware runs bottom-up in Starlette, so
    this one is entered first): a request should be counted against its budget
    before its body is examined, or an attacker gets unlimited attempts as long
    as each one is oversized.
    """
    window = rate_limit.limit_for(request.method, request.url.path)
    if window is not None:
        retry_after = window.hit(rate_limit.identity_for(request))
        if retry_after is not None:
            return JSONResponse(
                status_code=429,
                # Retry-After is what makes a 429 actionable rather than a
                # mystery: clients (and humans) learn when to come back.
                headers={"Retry-After": str(max(1, int(retry_after) + 1))},
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": (
                            f"Too many requests. Try again in "
                            f"{max(1, int(retry_after) + 1)}s."
                        ),
                    }
                },
            )
    return await call_next(request)


# --- Uniform error shape: { "error": { "code", "message" } }  (contract §1) ---
@app.exception_handler(HTTPException)
async def http_exc_handler(_: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        body = {"error": exc.detail}
    else:
        body = {"error": {"code": "error", "message": str(exc.detail)}}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "bad_request", "message": exc.errors()[0]["msg"]}},
    )


app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(conversation_router)
app.include_router(map_router)
app.include_router(prompts_router)
app.include_router(documents_router)
app.include_router(realtime_router)


@app.get("/health")
async def health():
    """Proves all three tiers: process up, DB round-trips, provider selected."""
    db_time = await db.db_ping()
    return {"status": "ok", "db_time": db_time, "provider": settings.llm_provider}


# --- Serve the built frontend (production image only) -------------------------
# The Docker build drops the Vite bundle at backend/static. When that directory
# exists, the API also serves the UI, so a self-hoster runs one container on one
# port instead of standing up a separate web server. In dev the directory is
# absent and this block is skipped entirely — `npm run dev` on :5173 is
# unaffected.
#
# Registered last, on purpose: every API router above is matched first, so the
# catch-all can never shadow a real endpoint.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

if _STATIC_DIR.is_dir():

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """Serve a real file if it exists, else index.html.

        Helix is a single-page app: the browser owns routes like
        /w/<id>/map, and no such file exists on disk. Returning index.html
        lets React Router resolve them — that is what makes a deep link or a
        page refresh work instead of 404ing.
        """
        # Unknown /api and /ws paths must stay JSON 404s. Without this they
        # would fall through and answer with the HTML page, which turns a
        # typo'd endpoint into a confusing parse error in the client.
        if full_path.startswith(("api/", "ws/")):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = (_STATIC_DIR / full_path).resolve()
        # Path-traversal guard: a request for ../../etc/passwd resolves outside
        # the static root, and is_relative_to catches exactly that.
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(_STATIC_DIR)
        ):
            return FileResponse(candidate)
        return FileResponse(_STATIC_DIR / "index.html")
