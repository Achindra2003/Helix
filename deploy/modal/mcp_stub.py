"""The demo MCP server, hosted.

    modal deploy deploy/modal/mcp_stub.py

`frontend/app/e2e/mcp-stub.mjs` is normally run on the presenter's laptop and
registered at `http://127.0.0.1:8123`. That cannot work against a *deployed*
Helix: the app dials out, nothing dials in, and the symptom is the
`502 mcp_unreachable` that room 2 stops on. The stub already reads the
platform's `PORT` for exactly this reason; this file is the platform.

It is deliberately a separate Modal app from `app.py`. The stub is a prop —
it exists to be pointed at, rewritten mid-demo (`/drift`), and thrown away —
and coupling its lifecycle to the product's would mean redeploying Helix to
change a tool description.

Register the URL this prints at **SETUP → Tool servers (MCP) → + Add a
server**, leaving the auth value empty; this server is open by design.
"""
import subprocess

import modal

PORT = 8123

image = (
    # Node, because the stub is a Node script. Modal needs Python in the image
    # for its own runtime, which `add_python` supplies as a standalone build —
    # the two never interact.
    modal.Image.from_registry("node:20-slim", add_python="3.11")
    .add_local_file(
        "frontend/app/e2e/mcp-stub.mjs", "/srv/mcp-stub.mjs", copy=True
    )
    # The stub reads PORT and, seeing it, prints "register this service's
    # public URL" instead of a loopback address that would be wrong here.
    .env({"PORT": str(PORT)})
)

app = modal.App("helix-mcp-stub")


@app.function(
    image=image,
    # One container, so `/drift` rewrites a description that the *next*
    # `tools/list` actually returns. Across replicas the demo's sharpest beat
    # would fire or not depending on which one Helix happened to reach.
    max_containers=1,
    # Next to Helix, for the same reason Helix sits next to Neon: this is a
    # server Helix *calls*, so the distance is charged to every tool call the
    # agent makes. The demo's tool ledger read `avg_latency_ms: 404` for a
    # server answering static JSON, which is a round trip rather than work.
    region="us-east",
    # Discovery and calls are bounded by Helix at 15s and 30s respectively
    # (api/tools/mcp.py), so a cold start here reads as a failed tool rather
    # than a slow one. Ten minutes of idle keeps it warm across a demo.
    scaledown_window=600,
    timeout=3600,
    # It answers static JSON. This is the platform minimum and it is plenty.
    cpu=0.125,
    memory=256,
)
@modal.concurrent(max_inputs=50)
@modal.web_server(PORT, startup_timeout=120)
def serve():
    subprocess.Popen(["node", "/srv/mcp-stub.mjs"])
