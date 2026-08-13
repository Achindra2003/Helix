# 00 — Pre-flight

Everything that must be true before you open your mouth. Fifteen minutes the
first time, three minutes every time after.

---

## 1. Start the stack

```
start-helix.bat
```

That frees ports 8000 and 5173 from any orphaned run, starts the backend on
`:8000` and the Vite dev server on `:5173`, each in its own window, and opens
the browser after eight seconds.

**Do not `docker build`.** You do not need it, and it is what took the C: drive
to zero bytes on 10 August. Running from source *is* the demo path.

Two windows stay open for the whole demo. Closing them stops Helix.

- Frontend, the one you present: <http://localhost:5173>
- Backend, useful as a fallback: <http://localhost:8000/docs>

**Verify:** the sign-in screen shows a green `api ✓` badge. That badge is the
frontend saying it can actually reach the backend — if it is red, nothing below
will work and no amount of clicking will fix it.

## 2. Check the provider and the models

Open `backend/.env`. It should read:

```
LLM_PROVIDER=groq
GROQ_MODEL=openai/gpt-oss-20b
DEEP_REASONING_MODEL=openai/gpt-oss-120b
```

**This matters and it is dated.** The two Llama models this file named until
12 August (`llama-3.1-8b-instant`, `llama-3.3-70b-versatile`) **stop serving on
free-tier Groq keys on 16 August 2026**. If you find them back in this file,
chat and Deep Reasoning will both fail on the day.

Do not open this file while screen-sharing — it holds live Groq and Tavily keys.

**If you want a keyless dry run** of the *shape* of the demo — every screen,
every button, no quota spent — set `LLM_PROVIDER=stub` and restart the backend.
The model echoes rather than answers, which is perfect for rehearsing clicks and
useless for showing quality. Set it back to `groq` before the real thing.

## 3. Start the MCP server (room 2 only)

A third window, left running and **visible** — it logs every call Helix makes
into it, which is half the point.

```
cd frontend/app
node e2e/mcp-stub.mjs
```

```
Helix demo MCP server — http://127.0.0.1:8123
  register that URL at  SETUP → Tool servers (MCP) → + Add a server
  tools: get_pull_request, list_issues, close_pull_request
  rewrite a description: http://127.0.0.1:8123/drift
  every call Helix makes is logged below — leave this window visible
```

No `npm install` — it uses Node built-ins only. It offers three tools on
purpose:

- **`get_pull_request`** — the one you will allow.
- **`list_issues`** — a second allowable tool, so "allowlist" looks like a
  choice rather than a switch.
- **`close_pull_request`** — the one you deliberately leave **un-allowed**, so
  you can say "the model cannot see this one at all" and mean it literally.

And `http://127.0.0.1:8123/drift` rewrites a tool's description mid-demo. That
is the sharpest thirty seconds in the whole product — see
[`02-DEV-TEAM.md`](02-DEV-TEAM.md) step 6.

**Verify:** open <http://127.0.0.1:8123> in a tab. You should get a plain-text
status page. Close the tab.

## 4. Two browsers

Non-negotiable if you want the demo to land. You need two *independent* logins,
which means two profiles, not two tabs.

| Window | Who | How |
|---|---|---|
| **A** | you — the owner | Your normal browser profile |
| **B** | a teammate | A second Chrome profile, or an incognito window, or Firefox |

Incognito is the fastest and it survives a whole demo fine. Put them side by
side on one screen if you can — the moment you are selling is *simultaneity*,
and alt-tabbing destroys it.

**Showing it to people in the room on their own laptops** — find your machine's
LAN address and have them open `http://<your-ip>:5173`. Everyone on the same
Wi-Fi becomes a real participant, which beats any recording.

```
ipconfig            # IPv4 Address, e.g. 192.168.1.14
```

## 5. Accounts

You have two options and they are for different audiences.

### Option A — the seeded research workspace (fastest, room 3 only)

Already ingested and ready:

- **`research@christ.edu`** / **`erisk-2025-demo`**
- Workspace: *"Depression Detection — eRisk 2025"*
- `paper.pdf` ingested — 22 chunks, grounding ready
- Three threads, plus a fork to `experiment-focal-loss` for the Map

**Demo on fresh threads.** The seeded threads are background — they are what
makes resurfacing and the Map stemma have something to find. Opening them on
stage shows your working rather than the product.

### Option B — register live (best for rooms 1 and 2)

Registering in front of people is itself a feature: an example workspace is
seeded automatically on every successful registration, so the first screen is
never empty. It takes fifteen seconds and it proves there is no setup.

Create these as you go:

| Window | Email | Role | Used in |
|---|---|---|---|
| A | `you@demo.helix` | Owner | all three rooms |
| B | `teammate@demo.helix` | Collaborator | rooms 1, 2 |
| B | `prof@demo.helix` | **Observer** | room 3 |

Any password of eight characters or more. Nothing is emailed.

**How to get window B into your workspace:** `TEAM` → `Outstanding invites` →
invite **as Collaborator** or **as Observer** → **copy link** → paste it into
window B. The role is carried by the link itself, which is worth saying out
loud — you are not inviting a person and then assigning a role, you are handing
out a role.

## 6. The map of the app

The left rail, top to bottom. Learn these six words and you can navigate without
looking.

| Rail | Where it goes | What lives there |
|---|---|---|
| **CHAT** | `/w/<id>` | Threads, branches, the composer, everything in rooms 1–3 |
| **MAP** | `/w/<id>/map` | The branch stemma and the decisions ledger |
| **PROMPTS** | `/w/<id>/library` | The prompt library |
| **DOCS** | `/w/<id>/docs` | The knowledge base — upload, metadata, search |
| **TEAM** | `/w/<id>/members` | Members, roles, invites, the permission matrix |
| **SETUP** | `/w/<id>/settings` | Provider/BYO key, Agent tools, Tool servers (MCP) |
| **FIND** | `Ctrl+K` | Search across every conversation |

Top bar: **What you missed** (the notice inbox) and **See it as** (role
preview). Bottom of the rail: your account.

---

## Pre-flight checklist

Run down this list immediately before presenting.

- [ ] `start-helix.bat` run; both windows still open
- [ ] Sign-in screen shows green `api ✓`
- [ ] `backend/.env` says `gpt-oss-20b` / `gpt-oss-120b`, `LLM_PROVIDER=groq`
- [ ] `node e2e/mcp-stub.mjs` running in a visible third window *(room 2)*
- [ ] Two browser windows, two different logins, side by side
- [ ] Window B already accepted its invite — do not spend stage time on this
- [ ] One rehearsal deep run spent at most; you have quota for the live one
- [ ] `backend/.env` **not** visible in any shared window
- [ ] Fresh threads ready; seeded threads left closed

---

## When something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Red `api ✗` on sign-in | Backend window died or never started | Look at the backend window; restart `start-helix.bat` |
| "address already in use" | Orphaned uvicorn/vite from a previous run | `start-helix.bat` frees 8000/5173 itself — just run it again |
| Chat returns an error mentioning the model | `.env` still names a retired Llama model | Fix `backend/.env` per step 2, restart the backend |
| Deep Reasoning says it needs a key | Workspace provider resolved with no key | `SETUP → Provider`, or check `GROQ_API_KEY` in `backend/.env` |
| Replies are nonsense echoes | `LLM_PROVIDER=stub` left over from a dry run | Set `groq`, restart the backend |
| MCP server shows an error on its card | Stub not running, or wrong port | Check the third window; the URL is `http://127.0.0.1:8123` |
| Agent never calls a tool | The model chose not to — it is a real model | Ask again, more directly: "Use your tools to read pull request 42" |
| Grounding returns nothing | Document still ingesting, or genuinely irrelevant | `DOCS` — wait for `ready`; "Nothing relevant" is the relevance floor working |
| Teammate's tokens don't appear in window A | Window A is not on that branch | Both windows must have the same thread open |

**One framing worth having ready.** If a grounded answer says nothing relevant
was found, that is not a failure — there is a calibrated relevance floor so an
unrelated question cannot drag the knowledge base into its prompt. Say that;
it turns a stumble into a feature.

---

Next: [`01-GENERAL-TEAM.md`](01-GENERAL-TEAM.md).
