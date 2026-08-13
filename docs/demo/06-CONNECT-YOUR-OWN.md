# 06 — Connecting your own things

Files `00`–`05` are performance scripts. They use a stub MCP server, a seeded
paper and a shared demo key, because a demo should not depend on anyone's
credentials being valid on the day.

This file is the other half: **how to point Helix at your own model, your own
GitHub, and your own documents.** It is instructions rather than a script — no
beats, no lines to say. Do these before a demo if you want the real thing on
screen, or after one when somebody asks *"could it talk to our actual GitHub?"*
and the honest answer is yes, here is how.

---

## 1. Your own model

`SETUP → Provider`, **owner only**. One key per workspace, encrypted at rest,
and never returned by any API afterwards — other members see only that it is
configured.

The one rule that decides everything: **Helix calls the model from the server,
not from your browser.** So the model has to be somewhere the Helix server can
reach. That gives three shapes.

### A — a hosted model (what the demo uses)

| Field | Value |
|---|---|
| Provider | `groq` |
| API key | your Groq key |
| Chat model | leave blank |
| Deep model | leave blank |

Blank models take the server's defaults, including the larger model for Deep
Reasoning. Get a free key at <https://console.groq.com>.

### B — your own inference server, reachable over the network

| Field | Value |
|---|---|
| Provider | `openai_compatible` |
| Base URL | `https://your-host/v1` — **must** start `http://` or `https://` |
| API key | whatever that endpoint expects (anything, if it does not check) |
| Chat model | **required** — the exact model name your server serves |
| Deep model | blank reuses the chat model |

**Chat model is not optional here.** `groq` and `ollama` have a server-side
default to fall back on; this provider has none, so leaving it blank sends an
empty model name and the error will not say so.

Works with OpenRouter, vLLM, LM Studio, or an Ollama exposed on your network.

### C — Ollama on your own machine

| Field | Value |
|---|---|
| Provider | `ollama` |
| Base URL | blank = `http://localhost:11434`, else the Ollama host |
| API key | leave blank |
| Chat model | the model you have pulled, e.g. `llama3` |

**`localhost` means the machine Helix runs on, not yours.** On a deployed Helix
that is a container in a data centre with no Ollama in it. This shape only works
when you are running Helix yourself, on the same machine or the same network.

> **Worth knowing:** if Helix can reach your Ollama, prefer **shape B** pointed
> at `http://your-ollama-host:11434/v1`. Ollama's native API has no chat-messages
> call, so Helix flattens the whole thread into one prompt for it
> (`render_messages_to_prompt`); the `/v1` surface takes real `system`/`user`/
> `assistant` turns. Same model, same machine, better answers. Deep Reasoning
> already uses `/v1` either way — it is only ordinary chat that takes the worse
> path when you select `ollama`.

**Test it.** The provider panel has a **Test** button that deliberately skips
the retry and circuit-breaker layer so you see the endpoint's actual error
rather than a polite one.

---

## 2. Your own GitHub, over MCP

This is the one people ask for. It works today, with no code changes, because
GitHub publishes a **remote** MCP server and Helix speaks that transport.

### Step 1 — a token

Create a **fine-grained personal access token** at
`github.com → Settings → Developer settings → Personal access tokens`.

Give it the least you can stand. Tools inherit the token's access exactly — an
MCP tool cannot read a repository the token cannot read, which makes the token
your real permission boundary. For a demo, read-only on one repository is
plenty; `repo` scope on everything is not.

### Step 2 — register it in Helix

`SETUP → Tool servers (MCP)` → **+ Add a server**.

| Field | Value |
|---|---|
| Name | `github` |
| Server URL | `https://api.githubcopilot.com/mcp/` |
| Auth header | `Authorization` |
| Auth value | `Bearer ghp_yourtokenhere` |

**The word `Bearer` is part of the value.** Helix sends the auth value exactly
as typed — it does not add a scheme. A token pasted on its own is the most
common reason discovery fails with a 401.

Click **Add and discover**.

> **Verified on the deployment, 14 August.** Registering
> `https://api.githubcopilot.com/mcp/` against
> <https://achindra2003--helix-serve.modal.run> reaches GitHub — a deliberately
> invalid token came back as *"server answered HTTP 401"*, which is GitHub
> refusing it rather than Helix failing to arrive. So this works from the hosted
> instance, not only from a laptop. Anyone with the link and their own token can
> connect their own repositories.

### Step 3 — deal with the fact that GitHub offers a lot of tools

The stub in `02-DEV-TEAM.md` offers three tools. GitHub's server offers many,
across toolsets including `repos`, `issues`, `pull_requests`, `actions`,
`code_security`, `discussions`, `notifications`, `orgs` and `users`.

Two consequences, both by design:

- **Nothing is offered to the model until you allow it.** The catalog will be
  long and everything in it starts un-allowed. Tick the handful you actually
  want — `get_pull_request`-style reads are the useful ones for a demo — and
  leave the rest. An un-allowed tool is not disabled; it does not exist to the
  model.
- **Everything discovered is sensitive by default**, so every call pauses for a
  human. That is right for a demo and tiring for daily use. An owner can demote
  a specific tool to non-sensitive, which is then a decision somebody made
  rather than a default nobody noticed. Demote reads if you like; do not demote
  anything that writes.

### Step 4 — use it

In a thread, **⚒ Agent**:

```
Use your tools to read pull request 42 in owner/repo, then say what it changes.
```

The tool call chip appears, the run stops for approval, and the call lands in
the workspace's tool ledger with its latency and who approved it.

### What this gives you, and what it does not

**It does:** let the agent *go and look* at your repository during a run —
files, issues, pull requests — with every call gated and recorded.

**It does not** put your repository into the workspace's memory. Grounding,
citations, resurfacing and Deep Reasoning's retrieval all read the **document
corpus**, and an MCP result is not in it. So:

- ordinary chat will not ground on your code
- typing a question will not resurface a matching file
- citation chips cannot point at a file and line

The accurate sentence is **"Helix can look things up in a repo; it does not hold
one in memory."** If you want a spec or a design doc to be *citable*, upload it
as a document (section 4) rather than reaching for it through MCP.

One more limit worth knowing before it surprises you on stage: a single tool
result is truncated at **6,000 characters**. Reading a large file returns the
first part of it, marked `[truncated]`.

### The privacy trade, said plainly

GitHub's remote server is hosted by GitHub, and the result flows
**GitHub → Helix → your model provider**. If your provider is Groq, your code
reaches Groq. That is fine for public repositories and wrong for the unreleased
work the dev room's pitch is about.

To keep the whole loop inside your walls: run the **self-hosted** GitHub MCP
server on your network *and* use provider shape B or C. Check first that the
self-hosted build can serve HTTP — Helix speaks Streamable HTTP over
`POST`, and cannot drive a `stdio` server. That is a deliberate limit, not an
omission: a `stdio` server means launching a third party's process on the box
holding every member's data.

---

## 3. Any other MCP server

The same four fields. A server works with Helix if it:

- speaks **Streamable HTTP** (JSON-RPC 2.0 over `POST`), answering `initialize`,
  `tools/list` and `tools/call` — an SSE-framed reply is fine, both are parsed;
- is **reachable from wherever Helix runs**, which on a deployed instance means
  publicly, not `127.0.0.1`;
- needs at most **one** header to authenticate. Helix stores a single
  header/value pair, so a server wanting two custom headers cannot be fully
  configured.

Discovery times out at 15 seconds and calls at 30. A hanging server degrades to
*"that tool failed"* rather than holding the run open.

Your own stub, if you want one to point at: `frontend/app/e2e/mcp-stub.mjs`
reads the platform's `PORT` and needs no build step and no dependencies, which
is why it can be hosted as a free Node service. `deploy/modal/mcp_stub.py` is
exactly that, in about twenty lines.

---

## 4. Your own documents

`DOCS` → upload. `txt`, `md`, code and `pdf`, up to 8 MB, one file at a time.

**Fill in the metadata** — author, year, title, identifier. It becomes
`cite_as`, and that one string is shared by the citation chip in the transcript,
the exported document, and the text the model is given. Skip it and your
citations read as filenames, which is the difference between evidence and an
attachment.

Wait for `ready` before asking anything of it: ingest chunks and embeds, and a
document mid-ingest is simply not in the corpus yet.

Then ask a question the document can answer. If Helix says nothing relevant was
found, that is the relevance floor working — an unrelated question cannot drag
the knowledge base into the prompt — and it is worth saying so rather than
retrying nervously.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `mcp_unreachable`, message *"server answered HTTP 401"* | **the server was reached and rejected your token.** Usually the auth value is missing its scheme | the value is `Bearer ghp_…`, not `ghp_…`. Read the *message*, not the code — `mcp_unreachable` is the one error code every discovery failure wears, including ones where the server answered perfectly well |
| `mcp_unreachable`, message *"could not reach the server: All connection attempts failed"* | genuinely not reachable *from Helix* | a deployed Helix cannot dial into your laptop; host the server |
| Discovery returns nothing | server does not implement `tools/list`, or is not Streamable HTTP | check with `curl` before blaming Helix |
| A tool is greyed out, *"description changed"* | the server rewrote what the model would be told | read the new text and accept it, or leave it un-armed. This is the feature working |
| The model ignores your tools | it is a real model making a real choice | ask more directly. Two attempts is normal — `rooms.mjs` retries for this reason |
| Tool result cut off | the 6,000-character cap | expected; ask for a narrower thing |
| Provider test fails with an empty model | `openai_compatible` with a blank chat model | it has no default — name the model |
| Everything worked, then stopped after a quiet period | serverless Postgres suspended | fixed by `pool_pre_ping`; if you self-host an older build, restart |
