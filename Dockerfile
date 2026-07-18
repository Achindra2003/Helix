# Helix — production image.
#
# Multi-stage: stage 1 builds the React bundle with Node; stage 2 is a Python
# image that serves that bundle *and* the API on one port. Node never ships —
# only the ~2 MB of built files cross the stage boundary. One container, one
# port, no reverse proxy, no separate frontend host.
#
#   docker build -t helix .
#   docker run -p 8000:8000 helix

# =============================================================================
# Stage 1 — build the frontend
# =============================================================================
FROM node:20-alpine AS frontend

WORKDIR /build

# package files first, on their own: Docker caches each instruction, and this
# layer only invalidates when dependencies change — not on every source edit.
# `npm ci` (not `install`) installs the exact lockfile versions, so the image
# is reproducible.
COPY frontend/app/package.json frontend/app/package-lock.json ./
RUN npm ci

COPY frontend/app/ ./

# The API is served from the same origin as the page, so the client must use
# relative URLs ("/api/..."). Empty string does that: api.ts falls back to a
# hardcoded http://127.0.0.1:8000 only when this is undefined, and "" is
# defined. This also makes the WebSocket URL relative, which is what lets
# realtime work behind any hostname or HTTPS without rebuilding.
ENV VITE_API_BASE=""

# `npm run build` = `tsc --noEmit && vite build` — the typecheck gate runs
# here too, so a type error fails the image build instead of shipping.
RUN npm run build

# =============================================================================
# Stage 2 — the runtime: Python API + the built frontend
# =============================================================================
FROM python:3.11-slim

# PYTHONDONTWRITEBYTECODE: no .pyc clutter in the image.
# PYTHONUNBUFFERED: logs appear immediately instead of sitting in a buffer —
# without it `docker logs` looks frozen during startup.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements before source, again for layer caching: editing a route should
# not re-run a multi-minute torch install.
COPY backend/requirements.txt backend/requirements-engine.txt ./

# torch first, and deliberately from PyTorch's CPU-only index.
#
# On Linux, plain `pip install torch` resolves to the CUDA build and drags in
# the NVIDIA GPU stack — cublas (445 MB), cusparselt (221 MB), nccl (206 MB),
# nvshmem (60 MB) and friends, several GB in total. None of it can ever run
# here: the container has no GPU, and torch exists only to execute a small
# MiniLM embedding model on CPU. (The trap is invisible on macOS, whose wheel
# has no CUDA at all — it appears only when building a Linux image.)
#
# Installing the CPU wheel first means sentence-transformers finds its torch
# dependency already satisfied on the next line and leaves it alone.
RUN pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install -r requirements.txt -r requirements-engine.txt

# Bake the MiniLM embedding model into the image (the decision recorded in
# README): ~100 MB now, in exchange for a container that runs fully offline
# and whose first Deep Reasoning request doesn't stall on a download.
# HF_HOME must be set *before* the download so the weights land somewhere
# predictable that the non-root user can read.
ENV HF_HOME=/opt/hf-cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Application code.
COPY backend/ ./

# The built bundle from stage 1. api/main.py mounts this directory when it
# exists, so the same code runs unchanged in dev (no dist/ -> API only).
COPY --from=frontend /build/dist ./static

# --- Security: drop root -----------------------------------------------------
# Everything above needed root (installing packages). Nothing below does. If
# the app is ever compromised, the attacker lands as an unprivileged user.
# /data is where SQLite lives — a separate directory so it can be a volume
# and survive container replacement.
RUN useradd --create-home --shell /bin/bash helix && \
    mkdir -p /data && \
    chown -R helix:helix /app /data /opt/hf-cache
USER helix

# Default to the zero-infra database, on the volume rather than in the image.
# compose overrides this for the Postgres setup.
ENV DATABASE_URL=sqlite+aiosqlite:////data/helix.db

# Where to persist an auto-generated signing secret when the operator has not
# set JWT_SECRET. On the data volume, so it survives restarts and image
# rebuilds — a secret regenerated per boot would log everyone out every time.
# This is what keeps `docker compose up` a single command while still giving
# every install its own unique secret instead of the public placeholder.
ENV JWT_SECRET_FILE=/data/.jwt_secret

EXPOSE 8000

# Lets Docker distinguish "running" from "alive". A hung app now shows as
# unhealthy instead of silently accepting traffic. Uses urllib rather than
# curl so the image needs no extra packages.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# No --reload: it watches the filesystem and restarts on change, which is a
# development convenience and a production liability.
# --host 0.0.0.0 is required — the default 127.0.0.1 would only accept
# connections from *inside* the container, making the published port useless.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
