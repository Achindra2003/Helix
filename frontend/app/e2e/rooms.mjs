// The three rooms, end to end.
//
// `docs/SCENARIOS.md` claims Helix serves a general team, a dev team and a
// research group, and grades every module against all three. The unit suite
// proves each module works; this proves the *journeys* work — which is a
// different question, because every gap that document found lived between two
// features that were each individually fine.
//
// So each room here is one continuous story told through the real HTTP surface:
// diverge and converge and leave with a record; discuss a change and review it
// and get an ADR; ground a claim in a paper and have the citation survive.
// Assertions are on the artifacts a room actually leaves with — the export, the
// report, the ledger — not on the calls that produced them.
//
// Isolated stack on 8023, throwaway DB, stub provider. Ports chosen to miss
// every other script in this directory.
//
// Set HELIX_E2E_API to run the same journeys against a stack that is already
// running — which for DEPLOY-V1 stage A2 is the Postgres container. The rooms
// are the assertion either way; the point of pointing them at a container is
// that a dialect difference shows up as a room failing rather than as a
// mysterious 500 in production. Two things change when the stack is external:
// nothing is booted here, and the MCP server the app calls back into has to be
// named by an address reachable *from the app*, which inside Docker is not
// 127.0.0.1 — hence HELIX_E2E_MCP_HOST.
//
// A stub hosted on a platform (deploy/modal/mcp_stub.py) is neither http nor
// on a port of its own: it is https on 443 behind the platform's hostname. So
// HELIX_E2E_MCP_URL names the whole URL when host-and-port cannot express it.
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";

const repo = "D:/Specialisation Project 4th Trimester";
const EXTERNAL = process.env.HELIX_E2E_API || "";
const API = EXTERNAL || "http://127.0.0.1:8023";
const MCP_HOST = process.env.HELIX_E2E_MCP_HOST || "127.0.0.1";
const MCP_URL = process.env.HELIX_E2E_MCP_URL || "";
const dbFile = join(tmpdir(), `helix-rooms-${Date.now()}.db`);
const children = [];
const failures = [];
let room = "";

function boot(cmd, args, opts) {
  const child = spawn(cmd, args, { stdio: "ignore", ...opts });
  children.push(child);
  return child;
}

function killTree(pid) {
  return new Promise((done) => {
    try {
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore" }).on("close", done);
    } catch { done(); }
  });
}

async function waitFor(url, label, tries = 160) {
  for (let i = 0; i < tries; i++) {
    try { if ((await fetch(url)).ok) return; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`${label} never came up at ${url}`);
}

/** Re-read something until it stops being in-flight. Returns the last value
 *  either way, so the caller's assertion is what reports the failure — a
 *  timeout here should not hide *what* the document ended up as. */
async function settle(read, done, tries = 60) {
  let last = await read();
  for (let i = 0; i < tries && !done(last); i++) {
    await new Promise((r) => setTimeout(r, 500));
    last = await read();
  }
  return last;
}

function check(ok, label) {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}`);
  if (!ok) failures.push(`[${room}] ${label}`);
}

function heading(name) {
  room = name;
  console.log(`\n── ${name} ${"─".repeat(Math.max(0, 58 - name.length))}`);
}

// --- the client -----------------------------------------------------------------

async function api(path, { token, method = "GET", body, raw } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const resp = await fetch(`${API}${path}`, {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (raw) return resp;
  const text = await resp.text();
  let parsed = null;
  try { parsed = JSON.parse(text); } catch { parsed = text; }
  if (!resp.ok) {
    const detail = typeof parsed === "string" ? parsed : JSON.stringify(parsed);
    throw new Error(`${method} ${path} → ${resp.status} ${detail.slice(0, 300)}`);
  }
  return parsed;
}

/** Consume an SSE response into its parsed frames. The turn endpoints stream. */
async function stream(path, { token, body }) {
  const resp = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`POST ${path} → ${resp.status} ${await resp.text()}`);
  const events = [];
  for (const line of (await resp.text()).split("\n")) {
    if (!line.startsWith("data:")) continue;
    try { events.push(JSON.parse(line.slice(5).trim())); } catch { /* keepalive */ }
  }
  return events;
}

// The cast's addresses are fixed because they read well in the output, and in a
// fresh database they are unique by construction — which is what the local run
// gets, a new SQLite file per run. An external stack keeps its rows, so the
// second run would collide on the very first register and never reach a single
// assertion. Plus-addressing keeps the name legible while making the row new.
const RUN_SUFFIX = EXTERNAL ? `+${Date.now().toString(36)}` : "";

async function signUp(email) {
  const address = RUN_SUFFIX ? email.replace("@", `${RUN_SUFFIX}@`) : email;
  const r = await api("/api/auth/register", {
    method: "POST", body: { email: address, password: "demo-password-1" },
  });
  return { token: r.token, id: r.user.id, email: address };
}

/** Put a second person in the room, the way a team actually does. */
async function invite(owner, wid, person, role) {
  const inv = await api(`/api/workspaces/${wid}/invites`, {
    token: owner.token, method: "POST", body: { role },
  });
  await api(`/api/invites/${inv.token}/accept`, { token: person.token, method: "POST" });
}

// --- a fake MCP server ----------------------------------------------------------
// Room 2 needs a repository-shaped tool without a GitHub credential. This speaks
// enough of the protocol to be discovered, allowlisted and called — which is the
// part of the claim under test ("MCP is a catalog source, not a subsystem").

function startMcpServer(port) {
  const TOOLS = [{
    name: "get_pull_request",
    description: "Read a pull request: title, body, and the diff it proposes.",
    inputSchema: {
      type: "object",
      properties: { number: { type: "integer", description: "PR number" } },
      required: ["number"],
    },
  }];
  const server = createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => { raw += c; });
    req.on("end", () => {
      const msg = JSON.parse(raw || "{}");
      const reply = (result) => {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ jsonrpc: "2.0", id: msg.id, result }));
      };
      if (msg.method === "initialize") {
        reply({ protocolVersion: "2024-11-05", capabilities: { tools: {} },
                serverInfo: { name: "fake-github", version: "0" } });
      } else if (msg.method === "tools/list") {
        reply({ tools: TOOLS });
      } else if (msg.method === "tools/call") {
        reply({ content: [{ type: "text",
          text: "PR #42 'Retry the ingest worker': adds a retry loop around the "
              + "document ingest call, with a fixed 3-attempt cap and no backoff." }] });
      } else {
        reply({});
      }
    });
  });
  return new Promise((done) => server.listen(port, () => done(server)));
}

// --- Room 1 — a general team ----------------------------------------------------
// "Open a question with no right answer, generate a lot of options quickly,
//  argue, and leave with a decision and a reason."

async function roomOne() {
  heading("Room 1 — a general team, discussing and brainstorming");

  const facilitator = await signUp("mara@rooms.helix.team");
  const teammate = await signUp("dev@rooms.helix.team");
  const ws = await api("/api/workspaces", {
    token: facilitator.token, method: "POST", body: { name: "Brainstorm" },
  });
  await invite(facilitator, ws.id, teammate, "collaborator");

  const conv = await api("/conversations", {
    token: facilitator.token, method: "POST",
    body: { workspace_id: ws.id, title: "How should onboarding work?", visibility: "shared" },
  });
  const main = conv.branch_id;

  // The thread is a shared object, not a private tab.
  const seenByTeammate = await api(`/conversations?workspace_id=${ws.id}`, { token: teammate.token });
  check(seenByTeammate.items.some((c) => c.id === conv.conversation_id),
    "a shared thread is visible to the whole workspace, not just its author");

  const turn = await stream(`/conversations/${main}/messages`,
    { token: facilitator.token, body: { prompt: "Give me three onboarding approaches." } });
  check(turn.some((e) => e.kind === "token"), "a reply streams token by token");
  check(turn.some((e) => e.kind === "assistant_node"), "and lands as a durable node");

  // A note is addressed to the room; the model must never read it.
  await api(`/conversations/${main}/notes`, {
    token: teammate.token, method: "POST",
    // The handle is the address's local part (api/mentions.py:handle_of), so
    // derive it from the account rather than writing "@mara" — otherwise the
    // mention silently addresses nobody whenever the cast is suffixed for an
    // external run.
    body: { content: `@${facilitator.email.split("@")[0]} I think the second one is closest, but it's expensive.` },
  });
  const notices = await api("/api/notices", { token: facilitator.token });
  check(notices.notices.length === 1, "an @mention leaves a notice for the person named");
  check(notices.notices[0]?.actor_email === teammate.email,
    "the notice says who asked");

  // The prompt library is the facilitator's artifact.
  const prompt = await api(`/workspaces/${ws.id}/prompts`, {
    token: facilitator.token, method: "POST",
    body: { title: "Adversarial", body: "Argue the strongest case against the above.",
            tags: ["review"] },
  });
  const fromPrompt = await stream(`/conversations/${main}/messages/from-prompt`,
    { token: facilitator.token, body: { prompt_id: prompt.id } });
  check(fromPrompt.some((e) => e.kind === "assistant_node"),
    "a saved prompt can be run as a turn without retyping it");

  // Diverge: three explorations off the same message.
  const history = await api(`/conversations/branches/${main}/history`, { token: facilitator.token });
  const forkPoint = history.nodes[history.nodes.length - 1].id;
  const names = ["guided tour", "sample data", "concierge"];
  const forks = [];
  for (const name of names) {
    forks.push(await api(`/conversations/${conv.conversation_id}/fork`, {
      token: facilitator.token, method: "POST",
      body: { from_node_id: forkPoint, name, intent: `try ${name}` },
    }));
  }
  const tree = await api(`/conversations/${conv.conversation_id}/branches`,
    { token: facilitator.token });
  check(tree.items.length === 4, `three explorations plus main (saw ${tree.items.length})`);

  // Converge: the primitive that was missing.
  await api(`/conversations/branches/${forks[1].branch_id}/vote`,
    { token: facilitator.token, method: "POST" });
  const tally = await api(`/conversations/branches/${forks[1].branch_id}/vote`,
    { token: teammate.token, method: "POST" });
  check(tally.votes.length === 2, `two members can back the same exploration (${tally.votes.length})`);

  await api(`/conversations/branches/${forks[0].branch_id}/vote`,
    { token: teammate.token, method: "POST" });
  const afterBoth = await api(`/conversations/${conv.conversation_id}/branches`,
    { token: teammate.token });
  const backedTwo = afterBoth.items.filter((b) => (b.votes ?? []).includes(teammate.id));
  check(backedTwo.length === 2,
    "backing is approval voting — one member may back several, and does not spend a vote");

  const withdrawn = await api(`/conversations/branches/${forks[0].branch_id}/vote`,
    { token: teammate.token, method: "POST" });
  check(withdrawn.backing === false && withdrawn.votes.length === 0,
    "and a backing can be withdrawn, so it is safe to cast on a hunch");

  // Decide, with a reason, and record the alternative that lost.
  await api(`/conversations/branches/${forks[1].branch_id}/resolve`, {
    token: facilitator.token, method: "POST",
    body: { status: "adopted", resolution: "Sample data gets them to value fastest." },
  });
  await api(`/conversations/branches/${forks[0].branch_id}/resolve`, {
    token: facilitator.token, method: "POST",
    body: { status: "abandoned", resolution: "A tour teaches the UI, not the job." },
  });
  await api(`/conversations/${conv.conversation_id}/conclude`, {
    token: facilitator.token, method: "POST",
    body: { conclusion: "Ship sample data first; revisit the tour after launch." },
  });

  const ledger = await api(`/workspaces/${ws.id}/decisions`, { token: teammate.token });
  check(ledger.items.length >= 2, `the ledger carries the verdicts (${ledger.items.length})`);

  const report = await (await api(`/workspaces/${ws.id}/export?format=md`,
    { token: facilitator.token, raw: true })).text();
  check(/Sample data gets them to value fastest/.test(report),
    "the export names the decision and its reason");
  check(/A tour teaches the UI, not the job/.test(report),
    "and the alternative that was rejected, which is half of why a decision holds up");
  check(/Ship sample data first/.test(report), "and the thread's conclusion");

  return { ws, conv, facilitator, teammate };
}

// --- Room 2 — a dev team --------------------------------------------------------
// "Decide a design, justify it later, review each other's work, and keep the
//  reasoning attached to the change it produced."

async function roomTwo(mcpPort) {
  heading("Room 2 — a dev team");

  const lead = await signUp("lead@rooms.helix.team");
  const ws = await api("/api/workspaces", {
    token: lead.token, method: "POST", body: { name: "Platform" },
  });
  const conv = await api("/conversations", {
    token: lead.token, method: "POST",
    body: { workspace_id: ws.id, title: "Retry the ingest worker", visibility: "shared" },
  });

  // The link to the change: a thread knows which change it is about.
  await api(`/conversations/${conv.conversation_id}/subject`, {
    token: lead.token, method: "POST", body: { subject: "PR #42 — retry the ingest worker" },
  });
  const stored = await api(`/conversations/${conv.conversation_id}`, { token: lead.token });
  check(stored.subject === "PR #42 — retry the ingest worker",
    "a thread can say which change it is about");

  // MCP as a catalog source: discovery, then the owner's allowlist.
  const added = await api(`/api/workspaces/${ws.id}/mcp`, {
    token: lead.token, method: "POST",
    body: { name: "github", url: MCP_URL || `http://${MCP_HOST}:${mcpPort}` },
  });
  const server = added.items[0];
  check(!!server, "an MCP server can be registered against a workspace");

  const synced = await api(`/api/workspaces/${ws.id}/mcp/${server.id}/sync`,
    { token: lead.token, method: "POST" });
  check(synced.summary.discovered >= 1,
    `discovery finds the server's tools (${synced.summary.discovered})`);

  const catalog = await api(`/api/workspaces/${ws.id}/settings/tools`, { token: lead.token });
  const pr = catalog.items.find((t) => t.name.includes("get_pull_request"));
  check(!!pr, "a discovered tool appears in the same catalog as the built-ins");
  check(pr?.source?.startsWith("mcp:"),
    `and is labelled with where it came from (${pr?.source})`);
  check(pr?.sensitive === true,
    "MCP tools default to sensitive — they leave the workspace by definition");
  check(pr?.allowed === false,
    "and are not offered to the model until an owner allows them");
  check(/pull request/i.test(pr?.description ?? ""),
    "the owner sees the tool's description verbatim — it is text the model will obey");

  // Allowlist it, then run the agent and watch the gate hold.
  await api(`/api/workspaces/${ws.id}/settings/tools`, {
    token: lead.token, method: "PUT", body: { allowed: [pr.name] },
  });
  // Whether the model reaches for a tool at all is the model's decision, and
  // this leg runs against a real one — so a single miss is a coin toss, not a
  // regression. Two attempts, and the assertions below are about what the
  // *gate* did once a call happened.
  let run = [];
  let called = [];
  for (let attempt = 0; attempt < 2 && called.length === 0; attempt++) {
    run = await stream(`/conversations/${conv.branch_id}/agent`, {
      token: lead.token,
      body: { prompt: "Use your tools to read pull request 42, then say what it changes." },
    });
    called = run.filter((e) => e.kind === "tool_call").map((e) => e.name);
  }
  check(called.length > 0, `the agent reached for a tool (called: ${called.join(", ") || "none"})`);
  check(called.every((n) => n.includes("get_pull_request")),
    "and only allowlisted tools were offered to it — an un-allowed tool does not exist to the model");

  const waiting = run.find((e) => e.kind === "waiting");
  check(!!waiting, "a sensitive call pauses the run for a human");
  const runId = run.find((e) => e.kind === "agent_run")?.run_id;
  if (waiting && runId) {
    const resumed = await stream(`/conversations/agent/runs/${runId}/approve`,
      { token: lead.token, body: { approved: true } });
    check(resumed.some((e) => e.kind === "tool_result"),
      "and the approved call then runs, streaming the continuation");
  }

  // The record the approval leaves — the half that had no telemetry at all.
  const usage = await api(`/api/workspaces/${ws.id}/usage`, { token: lead.token });
  check(Array.isArray(usage.tools), "the workspace can account for what its agents ran");
  check(usage.tools.some((t) => t.tool.includes("get_pull_request")),
    `the MCP call is in the ledger (${JSON.stringify(usage.tools)})`);

  // Review as a reasoning mode, not a second agent.
  const modes = await api("/conversations/deep/modes", { token: lead.token });
  check(modes.modes.some((m) => m.id === "review"), "Review is one of the reasoning modes");
  await stream(`/conversations/${conv.branch_id}/deep`,
    { token: lead.token, body: { prompt: "Review this change against what the issue asked.",
                                 mode: "review" } });

  // The archive holds both kinds. An agent run leaving no durable artefact was
  // the gap Stage 2 closed, so its presence here is part of the claim.
  const runs = await api(`/conversations/${conv.conversation_id}/deep/runs`, { token: lead.token });
  const records = await Promise.all(runs.items.map((r) =>
    api(`/conversations/deep/runs/${r.id}/record`, { token: lead.token })));
  const review = records.find((r) => r.provenance?.mode === "review");
  check(!!review, "a review is archived as a review, findable months later");
  check(runs.items.length >= 2,
    `and the agent run is in the same archive (${runs.items.length} runs)`);

  // The ADR.
  await api(`/conversations/branches/${conv.branch_id}/resolve`, {
    token: lead.token, method: "POST",
    body: { status: "adopted", resolution: "Retry with backoff; a fixed cap hides the outage." },
  });
  const adr = await (await api(`/workspaces/${ws.id}/export?format=md`,
    { token: lead.token, raw: true })).text();
  check(/Retry with backoff/.test(adr), "the decision export carries the verdict and its reason");
  check(/PR #42/.test(adr),
    "and the change the decision was about — an ADR that cannot name its change decays into folklore");

  return { ws, conv, lead };
}

// --- Room 3 — a research group --------------------------------------------------
// "Read papers, explore an approach across threads, compare methods, and produce
//  claims that must be traceable to sources."

async function roomThree() {
  heading("Room 3 — a research group");

  const pi = await signUp("pi@rooms.helix.team");
  const supervisor = await signUp("prof@rooms.helix.team");
  const ws = await api("/api/workspaces", {
    token: pi.token, method: "POST", body: { name: "Lab" },
  });
  await invite(pi, ws.id, supervisor, "observer");

  const PAPER =
    "Retrieval-augmented generation grounds an answer in retrieved passages. "
    + "The relevance floor is calibrated on a golden set so an unrelated question "
    + "does not drag the knowledge base into its prompt. Chunk overlap of fifty "
    + "tokens preserved cross-section context in our measurements.";
  const form = new FormData();
  form.append("file", new Blob([PAPER], { type: "text/plain" }), "grounding-2020.txt");
  const doc = await (await fetch(`${API}/api/workspaces/${ws.id}/documents`, {
    method: "POST", headers: { Authorization: `Bearer ${pi.token}` }, body: form,
  })).json();
  // Polled rather than asserted outright. The stack booted above sets
  // DOCUMENTS_INGEST_INLINE, so upload returns already-chunked; a real
  // deployment does that work in the background and answers "pending" first.
  // Waiting covers both, and asserting after the wait still fails an ingest
  // that never finishes — which is the thing worth catching.
  const ingested = await settle(
    () => api(`/api/workspaces/${ws.id}/documents/${doc.id}`, { token: pi.token }),
    (d) => d.status !== "processing",
  );
  check(ingested.status === "ready",
    `a paper ingests and chunks (${ingested.chunk_count} chunks)`);

  // A filename is not a citation.
  const catalogued = await api(`/api/workspaces/${ws.id}/documents/${doc.id}`, {
    token: pi.token, method: "PATCH",
    body: { authors: "Lewis et al.", year: "2020", doc_title: "Retrieval-Augmented Generation" },
  });
  check(catalogued.cite_as === "Lewis et al. (2020)",
    `a catalogued source cites as a reference (${catalogued.cite_as})`);

  const conv = await api("/conversations", {
    token: pi.token, method: "POST",
    body: { workspace_id: ws.id, title: "Grounding", visibility: "shared" },
  });
  const turn = await stream(`/conversations/${conv.branch_id}/messages`,
    { token: pi.token, body: { prompt: "What is the relevance floor calibrated on?" } });
  const grounding = turn.find((e) => e.kind === "grounding");
  check(!!grounding, "a grounded reply announces its sources while it streams");

  // The finding this whole document called the most important one.
  const reread = await api(`/conversations/branches/${conv.branch_id}/history`, { token: pi.token });
  const reply = reread.nodes[reread.nodes.length - 1];
  check((reply.citations ?? []).length > 0,
    "and the sources are still on the node when the thread is re-read");
  check(reply.citations?.[0]?.cite_as === "Lewis et al. (2020)",
    `the stored citation is a reference, not a filename (${reply.citations?.[0]?.cite_as})`);

  // Two documents behind one route: `branch` gives the fair copy of a path,
  // its absence gives the whole thread as a decision report. A research team
  // hands over both, so the evidence has to be in both.
  const transcript = await (await api(
    `/conversations/${conv.conversation_id}/export?format=md&branch=${conv.branch_id}`,
    { token: pi.token, raw: true })).text();
  check(/Grounded on/i.test(transcript) && /Lewis et al\. \(2020\)/.test(transcript),
    "the exported transcript carries the evidence under the claim");
  const convReport = await (await api(
    `/conversations/${conv.conversation_id}/export?format=md`,
    { token: pi.token, raw: true })).text();
  check(/Lewis et al\. \(2020\)/.test(convReport),
    "and so does the thread's decision report");

  // The supervisor: read-only, but not mute.
  const note = await api(`/conversations/${conv.branch_id}/notes`, {
    token: supervisor.token, method: "POST",
    body: { content: "That floor needs a citation to the calibration set." },
  });
  check(note.role === "note", "an Observer can leave a margin note");
  const blocked = await api(`/conversations/${conv.branch_id}/messages`,
    { token: supervisor.token, method: "POST", body: { prompt: "answer me" }, raw: true });
  check(blocked.status === 403, "and still cannot address the model");

  // A note is for the room. It must never reach the model.
  const after = await stream(`/conversations/${conv.branch_id}/messages`,
    { token: pi.token, body: { prompt: "What did chunk overlap preserve?" } });
  check(after.some((e) => e.kind === "assistant_node"),
    "the thread keeps working with a note in it");

  return { ws, conv, pi, supervisor };
}

// --- run ------------------------------------------------------------------------

let mcp;
async function main() {
  mcp = await startMcpServer(8123);
  if (EXTERNAL) {
    console.log(`running against ${API} (MCP callback host: ${MCP_HOST})`);
  } else {
    boot(join(repo, "backend", ".venv", "Scripts", "python.exe"),
      ["-m", "uvicorn", "api.main:app", "--port", "8023"],
      { cwd: join(repo, "backend"), env: {
        ...process.env, LLM_PROVIDER: "stub", HELIX_DEV: "1",
        DOCUMENTS_INGEST_INLINE: "1",
        DATABASE_URL: `sqlite+aiosqlite:///${dbFile.replace(/\\/g, "/")}`,
      } });
  }
  await waitFor(`${API}/health`, "backend");

  await roomOne();
  await roomTwo(8123);
  await roomThree();
}

main()
  .catch((err) => { console.error("\n" + err.stack); failures.push(`[${room}] ${err.message}`); })
  .finally(async () => {
    if (mcp) mcp.close();
    await Promise.all(children.map((c) => killTree(c.pid)));
    console.log(
      failures.length
        ? `\n${failures.length} FAILED:\n  - ${failures.join("\n  - ")}`
        : "\nall three rooms hold",
    );
    process.exit(failures.length ? 1 : 0);
  });
