"""Helix on Modal.

    modal deploy deploy/modal/app.py

Modal is a serverless platform, and Helix is a stateful long-lived server, so
three of the choices below are load-bearing rather than stylistic. Each one is
commented where it is made.

**Why `asgi_app` and not `web_server`.** Modal offers both, and the choice was
made the other way first, for a reason that turned out to be the lesser one.

`@modal.web_server` runs our own uvicorn and proxies to it, with a 3600-second
request ceiling against `asgi_app`'s **150 seconds**. That looked decisive. But
that proxy does not carry WebSockets: the realtime socket opens and closes again
within about two seconds, measured, while the identical build holds it open
indefinitely locally and under `asgi_app`. Presence, live fan-out and watching a
teammate's run — the whole reason the workspace feels shared — are on that
socket.

So `asgi_app`, and the 150-second ceiling is bought off rather than lived with:
`DEEP_REASONING_DEADLINE_S` below is set under it, so a long run halts *itself*
cleanly with `stop_reason="deadline"` before the platform can sever the stream.
Deep runs also execute server-side and survive a dropped client, so the failure
mode even then is a reconnect rather than a lost run.

**Why the image comes from GHCR.** `.github/workflows/release.yml` already
builds and tests it, and `Image.from_dockerfile` would re-implement a
multi-stage build whose `EXPOSE` and `HEALTHCHECK` instructions Modal does not
support anyway. The published image is public, so no registry secret is needed.

**Why one container, forever.** See `max_containers` below. This is the same
constraint the Dockerfile's `--workers 1` comment describes, for the same
reason, and on Modal it is easier to get wrong because the platform's default
is to scale out.
"""
import modal

# The image CI published. Bump this string after tagging a new release; that is
# the whole redeploy procedure.
IMAGE_TAG = "ghcr.io/achindra2003/helix:v0.9.0-rc3"

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
            # --- the 150s ceiling, no longer bought off --------------------
            # Modal still cuts any HTTP request at 150 seconds, and this used
            # to carry `DEEP_REASONING_DEADLINE_S=120` so that a long run
            # halted itself before the platform could sever the stream. That
            # traded a *product* capability for a *hosting* limit: the
            # deployment shipped a smaller reasoning budget than the product
            # has.
            #
            # It is no longer needed. The client now treats a cut stream as
            # what it is — a dropped transport over a run that is still
            # executing server-side — and reattaches from the last event it
            # read (`useDeepRun.ts`, `?after=`). A run that outlives one
            # request is picked back up rather than reported as finished, so
            # the deadline can be the product's own again.
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
    # **Put the container next to the database.** Without this, Modal places it
    # wherever it has room, and the distance to Neon (`us-east-2`) is then a
    # matter of luck. Measured, same image, same database, one probe container
    # against another: `SELECT 1` cost **2.5 ms** in Ohio and **334 ms**
    # elsewhere. Nothing in the application is slow — but a fresh session per
    # store operation means one registration makes 19 pool checkouts and 58
    # statements, and a fresh session per checkout means `pool_pre_ping` pays
    # the round trip twice. At 334 ms that arithmetic is a twelve-second
    # sign-up; at 12.8 ms it is about a second.
    #
    # `us-east` is the narrowest region Modal offers here, and Neon is in
    # `us-east-2` — near enough. The broad `"us"` measured ~35 ms, which would
    # also be acceptable and costs 1.5x rather than 1.75x; the narrow one is
    # worth it while the container only runs when someone is using it.
    region="us-east",
    # Scale to zero when idle, and that is deliberate rather than a compromise.
    # Region pinning multiplies the compute price by 1.75, so an always-warm
    # container would cost roughly $45/month against $30 of Starter credits.
    # Billed per second of actual uptime instead, the same box costs about
    # $0.11/hour — call it 270 hours a month inside the credits, which is far
    # more than a demo instance is ever awake for.
    #
    # The price is that the first visitor after an idle period pays a cold
    # start (~25 s). Before a demo, open the URL five minutes early; that is
    # already step one of the pre-flight in docs/demo/05-ON-THE-DEPLOYMENT.md.
    min_containers=0,
    # Ten minutes of idle before the container is released. Long enough that a
    # pause between demo beats never costs a cold start.
    scaledown_window=600,
    # The *container's* budget, not the request's — a WebSocket held open for a
    # working session is one long-lived input, and this is what bounds it. HTTP
    # requests are capped at 150s by the platform regardless; see the deep-run
    # deadline above.
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
@modal.asgi_app()
def serve():
    """Hand Modal the same FastAPI app the image's CMD would have served.

    There is no uvicorn here and no `--workers 1`: Modal runs the ASGI app in
    one container, and `max_containers=1` above is what carries that decision
    now. The application is imported unchanged.
    """
    from api.main import app as fastapi_app

    return fastapi_app
