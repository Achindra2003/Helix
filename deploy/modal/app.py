"""Helix on Modal.

    modal deploy deploy/modal/app.py

Modal is a serverless platform, and Helix is a stateful long-lived server, so
three of the choices below are load-bearing rather than stylistic. Each one is
commented where it is made.

**Why `web_server` and not `asgi_app`.** Modal offers both. `@modal.asgi_app`
wraps the ASGI app and enforces a **150-second HTTP request timeout** on every
request — which Helix would hit on a long Deep Reasoning run and hit instantly
on a guided run paused for steering. `@modal.web_server` instead runs our own
uvicorn inside the container and proxies to it, and that proxy's timeout is
**3600 seconds**. Same uvicorn invocation as the Dockerfile's `CMD`; nothing in
the application changes.

**Why the image comes from GHCR.** `.github/workflows/release.yml` already
builds and tests it, and `Image.from_dockerfile` would re-implement a
multi-stage build whose `EXPOSE` and `HEALTHCHECK` instructions Modal does not
support anyway. The published image is public, so no registry secret is needed.

**Why one container, forever.** See `max_containers` below. This is the same
constraint the Dockerfile's `--workers 1` comment describes, for the same
reason, and on Modal it is easier to get wrong because the platform's default
is to scale out.
"""
import subprocess

import modal

# The image CI published. Bump this string after tagging a new release; that is
# the whole redeploy procedure.
IMAGE_TAG = "ghcr.io/achindra2003/helix:v0.9.0-rc2"

image = (
    modal.Image.from_registry(IMAGE_TAG)
    # `from_registry` does not carry the image's WORKDIR, and `api.main` is only
    # importable from /app.
    .workdir("/app")
    .env(
        {
            # The published image defaults to the zero-setup stub provider so
            # that `docker run` works with no configuration. A deployment wants
            # the real one; the key itself arrives via the secret below.
            "LLM_PROVIDER": "groq",
            # --- memory -----------------------------------------------------
            # Set here rather than only in the Dockerfile so this deployment
            # gets them without waiting for a new image build.
            #
            # torch sizes its thread pool from `os.cpu_count()`, which reports
            # the host's cores rather than the fraction of a core this
            # container is metered at, and each thread carries its own scratch
            # arena. MALLOC_ARENA_MAX is the same problem one layer down: glibc
            # opens arenas per core and returns freed memory to the arena
            # rather than the kernel, so peak usage becomes resident usage.
            #
            # This is what took the 512 MB Render instance down; see
            # docs/demo/05-ON-THE-DEPLOYMENT.md.
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "MALLOC_ARENA_MAX": "2",
        }
    )
)

app = modal.App("helix")


@app.function(
    image=image,
    # DATABASE_URL, GROQ_API_KEY and JWT_SECRET. Created out of band so no
    # secret value is ever written into this repository:
    #   modal secret create helix DATABASE_URL=... GROQ_API_KEY=... JWT_SECRET=...
    #
    # JWT_SECRET matters more than it looks. Unset, the image falls back to
    # generating one into JWT_SECRET_FILE on disk — and this container has no
    # persistent disk, so every replacement would silently log the whole team
    # out. Set it explicitly and tokens survive a redeploy.
    secrets=[modal.Secret.from_name("helix")],
    # **One container, and never two.** Presence and workspace fan-out are an
    # in-process dict (`api/realtime.py`), and RunManager — which owns "stop
    # this run", the per-workspace concurrency cap and the live monitor — is a
    # module singleton. A second container would serve those from whichever
    # replica took the request: the app would look like it scaled and would
    # quietly split one workspace into two rooms that cannot see each other.
    max_containers=1,
    # Scale to zero when idle, which is what makes this free. The first visitor
    # after an idle period pays a cold start, so before a demo either send one
    # request five minutes early or set `min_containers=1` for the day.
    min_containers=0,
    # Ten minutes of idle before the container is released. Long enough that a
    # pause between demo beats never costs a cold start.
    scaledown_window=600,
    # Matches the web_server proxy's own 3600s ceiling. A request cannot outlive
    # the proxy, so a smaller number here would only mean two different limits.
    timeout=3600,
    # ~570 MB resident once anything semantic has run (docs/DEPLOY-RUNBOOK.md),
    # plus room for an embedding batch during document ingest. 2 GB is four
    # times the free Render tier that was being OOM-killed, and memory is
    # billed per second only while the container is up.
    cpu=1.0,
    memory=2048,
)
# Without this, Modal hands a container one request at a time and a web server
# would serve exactly one visitor. Streaming replies and open WebSockets both
# hold an input for their whole lifetime, so the ceiling has to comfortably
# exceed the number of people in the room.
@modal.concurrent(max_inputs=100)
@modal.web_server(
    8000,
    # A cold start pulls a ~2.5 GB image and boots uvicorn. The default of five
    # seconds is for a hello-world.
    startup_timeout=300,
)
def serve():
    """Start the same uvicorn the Dockerfile's CMD starts, and return.

    `web_server` expects this function to launch a listener on the declared
    port and exit; Modal proxies to it from there. `--workers 1` is the same
    decision as `max_containers=1`, one level down.
    """
    subprocess.Popen(
        [
            "uvicorn",
            "api.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--workers",
            "1",
        ],
        cwd="/app",
    )
