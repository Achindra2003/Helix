from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db
from .config import settings
from .conversation.map import router as map_router
from .conversation.router import router as conversation_router
from .documents.router import router as documents_router
from .prompts.router import router as prompts_router
from .realtime import router as realtime_router
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
