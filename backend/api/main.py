from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import db
from .config import settings
from .providers import get_provider
from .routers import auth, workspaces


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.get("/health")
async def health():
    """Proves all three tiers: process up, DB round-trips, provider selected."""
    db_time = await db.db_ping()
    return {"status": "ok", "db_time": db_time, "provider": settings.llm_provider}


class ChatRequest(BaseModel):
    prompt: str


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Stream a reply token-by-token as SSE. Week-0 slice; grows into contract §7."""
    provider = get_provider()

    async def event_stream():
        async for chunk in provider.stream(req.prompt):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
