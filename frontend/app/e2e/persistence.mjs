// What survives replacing the container.
//
// `docker compose down && up` destroys the container and builds a new one from
// the image. Everything the old one held in its own filesystem goes with it;
// only the named volume at /data comes back. This script is the check that the
// right things are on that volume, and it is written in two phases because the
// interesting moment happens between them:
//
//   node e2e/persistence.mjs seed   <state.json>
//   docker compose down && docker compose up -d
//   node e2e/persistence.mjs verify <state.json>
//
// Three claims, each of which has a specific way of being wrong:
//
//   1. The account survives. Ordinary database persistence — if this fails the
//      volume is not mounted at all and nothing else here matters.
//   2. The *old token* still works. This is the sharper one, and the reason
//      phase two does not simply log in again: a fresh login would pass even
//      if the server had generated a brand new signing secret on boot. Reusing
//      the token issued before the restart is what proves JWT_SECRET_FILE
//      landed on the volume. A regenerated secret logs the whole team out, and
//      logging in again is precisely the action that hides it.
//   3. A paused guided run can still be steered. The run's state lives in the
//      LangGraph checkpoint file, which until recently was written relative to
//      the working directory — /app, the image layer — so a run paused for a
//      human vanished on every deploy. CHECKPOINT_PATH now names the volume;
//      this is the step that proves it, and it is exactly the walk-away-and-
//      come-back the guided mode exists for.
//
// HELIX_E2E_API points it somewhere other than the default container port.
import { readFileSync, writeFileSync } from "node:fs";

const API = process.env.HELIX_E2E_API || "http://127.0.0.1:8000";
const [phase, stateFile] = process.argv.slice(2);
const failures = [];

function check(ok, label) {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}`);
  if (!ok) failures.push(label);
}

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

/** Consume an SSE response into its parsed frames. */
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

// --- phase one ------------------------------------------------------------------

async function seed() {
  console.log(`\n── seeding ${API} ${"─".repeat(40)}`);
  const email = `persist-${Date.now()}@rooms.helix.team`;
  const password = "demo-password-1";

  const reg = await api("/api/auth/register", {
    method: "POST", body: { email, password },
  });
  const token = reg.token;
  const ws = await api("/api/workspaces", {
    token, method: "POST", body: { name: "Persistence" },
  });
  const conv = await api("/conversations", {
    token, method: "POST",
    body: { workspace_id: ws.id, title: "does this survive a restart?", visibility: "shared" },
  });

  const turn = await stream(`/conversations/${conv.branch_id}/messages`,
    { token, body: { prompt: "Say something durable." } });
  check(turn.some((e) => e.kind === "assistant_node"), "a reply lands as a durable node");

  // Guided: the run pauses at a steer checkpoint and ends its stream on
  // `waiting`, with no assistant node yet. That paused state is the thing
  // under test — it has to be rebuilt from disk by the *next* container.
  const state = { email, password, token, wid: ws.id, cid: conv.conversation_id,
                  branchId: conv.branch_id, runId: null };
  try {
    const deep = await stream(`/conversations/${conv.branch_id}/deep`,
      { token, body: { prompt: "Compare two ways to onboard a new teammate.", steerable: true } });
    state.runId = deep.find((e) => e.kind === "deep_run")?.run_id ?? null;
    const paused = deep.some((e) => e.kind === "waiting");
    check(!!state.runId, `a guided deep run starts (${state.runId ?? "no run_id"})`);
    check(paused, "and pauses for steering rather than running to completion");
  } catch (err) {
    // Deep Reasoning needs a real model: the stub provider has no key and the
    // route answers 503. Recorded rather than failed, so the two claims that
    // do not need a provider still get checked on a default install.
    console.log(`  --   guided run skipped: ${String(err.message).slice(0, 160)}`);
  }

  writeFileSync(stateFile, JSON.stringify(state, null, 2));
  console.log(`\nstate written to ${stateFile}`);
  console.log("now: docker compose down && docker compose up -d");
}

// --- phase two ------------------------------------------------------------------

async function verify() {
  console.log(`\n── verifying ${API} after restart ${"─".repeat(28)}`);
  const state = JSON.parse(readFileSync(stateFile, "utf8"));

  // The account itself.
  const login = await api("/api/auth/login", {
    method: "POST", body: { email: state.email, password: state.password },
  });
  check(!!login.token, "the account survives replacing the container");

  // The token issued *before* the restart. A new signing secret would reject
  // it, and nothing else in this script would notice.
  const me = await api("/api/me", { token: state.token, raw: true });
  check(me.status === 200,
    `a token issued before the restart is still valid (${me.status}) — the signing secret persisted`);

  // The thread and its history.
  const history = await api(`/conversations/branches/${state.branchId}/history`,
    { token: login.token });
  check((history.nodes?.length ?? 0) > 0,
    `the thread still has its messages (${history.nodes?.length ?? 0} nodes)`);

  // The paused run, rebuilt from the checkpoint file by a process that never
  // saw it start.
  if (!state.runId) {
    console.log("  --   no guided run was seeded; checkpoint survival unchecked");
  } else {
    const steered = await api(`/conversations/deep/runs/${state.runId}/steer`, {
      token: login.token, method: "POST", raw: true,
      body: { guidance: "Focus on the first week." },
    });
    check(steered.status === 200,
      `a run paused before the restart can still be steered (${steered.status})`);
  }
}

const run = phase === "seed" ? seed : phase === "verify" ? verify : null;
if (!run || !stateFile) {
  console.error("usage: node e2e/persistence.mjs <seed|verify> <state.json>");
  process.exit(2);
}
run()
  .catch((err) => { console.error("\n" + err.stack); failures.push(err.message); })
  .finally(() => {
    console.log(failures.length
      ? `\n${failures.length} FAILED:\n  - ${failures.join("\n  - ")}`
      : "\nall checks hold");
    process.exit(failures.length ? 1 : 0);
  });
