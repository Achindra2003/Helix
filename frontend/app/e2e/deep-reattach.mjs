// Does a deep run survive losing its stream?
//
//   node e2e/deep-reattach.mjs [baseUrl]
//   node e2e/deep-reattach.mjs https://achindra2003--helix-serve.modal.run
//
// A deep run executes server-side and outlives the request that started it —
// but only if the client understands that. It did not: any stream that ended
// without a `complete` frame was treated as the run ending, reported as "done"
// when the read finished cleanly and "error" when it threw, while the run went
// on to finish perfectly well with nobody watching.
//
// That mattered because the deployment cuts every HTTP request at 150 seconds,
// which is shorter than a deep run is allowed to think. The workaround was to
// shrink the run's own budget below the platform's ceiling — paying for a
// hosting limit with a product capability. The client now reattaches instead,
// and this is the contract it depends on:
//
//   GET /conversations/deep/runs/{id}/stream?after=N
//
// replays from index N and then follows live, so a client that has read N
// events can carry on from exactly there. This proves the two halves that make
// that safe: nothing is lost across the cut, and nothing arrives twice.
const API = process.argv[2] || process.env.HELIX_E2E_API || "http://127.0.0.1:8000";

const api = async (path, opts = {}) => {
  const res = await fetch(API + path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status} ${(await res.text()).slice(0, 300)}`);
  return res.json();
};

const failures = [];
const check = (ok, what) => {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${what}`);
  if (!ok) failures.push(what);
};

/** Read SSE frames from a response, handing each decoded event to `onEvent`.
 *  Stops early — and aborts the request — once `stopAfter` events have been
 *  seen, which is how this simulates a cut stream. */
async function readEvents(res, { stopAfter = Infinity, onEvent } = {}) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let count = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let i;
      while ((i = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, i);
        buffer = buffer.slice(i + 2);
        const line = frame.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const payload = line.slice(6);
        count += 1;
        onEvent?.(payload === "[DONE]" ? { kind: "done" } : JSON.parse(payload), count);
        if (count >= stopAfter) return count;
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
  return count;
}

const stamp = Date.now().toString(36);
const auth = await api("/api/auth/register", {
  method: "POST",
  body: { email: `reattach+${stamp}@rooms.helix.team`, password: "demo-password-1" },
});
const token = auth.token;
const workspace = await api("/api/workspaces", {
  method: "POST", token, body: { name: "Deep reattach" },
});
const conversation = await api("/conversations", {
  method: "POST", token,
  body: { workspace_id: workspace.id, title: "reattach", visibility: "shared" },
});
const branchId = conversation.branch_id;

console.log(`deep-run reattach against ${API}\n`);

// --- start a run, then walk away from its stream mid-flight ----------------
const started = await fetch(`${API}/conversations/${branchId}/deep`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({
    prompt: "Compare two database choices for a small team, and commit to one.",
    steerable: false,
  }),
});
check(started.ok, `a deep run starts (HTTP ${started.status})`);
if (!started.ok) process.exit(1);

const firstHalf = [];
let runId = "";
const readBeforeCut = await readEvents(started, {
  stopAfter: 4,
  onEvent: (ev) => {
    firstHalf.push(ev);
    if (ev.kind === "deep_run") runId = ev.run_id;
  },
});
check(!!runId, `the run announces an id (${runId.slice(0, 12)}…)`);
check(readBeforeCut === 4, `read ${readBeforeCut} events, then dropped the stream`);

// The run must still be alive: the whole point is that it does not depend on
// whoever was reading it.
const status = await api(`/conversations/deep/runs/${runId}/status`, { token });
check(
  ["running", "queued", "paused"].includes(status.status) || status.status === "done",
  `the run outlived its reader (status: ${status.status})`,
);

// --- pick it back up from exactly where we stopped reading -----------------
const resumed = await fetch(
  `${API}/conversations/deep/runs/${runId}/stream?after=${readBeforeCut}`,
  { headers: { Authorization: `Bearer ${token}` } },
);
check(resumed.ok, `reattaching from index ${readBeforeCut} is accepted (HTTP ${resumed.status})`);
if (!resumed.ok) process.exit(1);

const secondHalf = [];
await readEvents(resumed, { onEvent: (ev) => secondHalf.push(ev) });

// --- the two properties that make reattaching safe -------------------------
// Nothing repeated: `after` is an index into the log, so the continuation must
// not begin by replaying what the first reader already had. A client that
// reattached and got duplicates would draw every step twice in the monitor.
const firstKinds = firstHalf.map((e) => e.kind).join(",");
const secondStart = secondHalf.slice(0, firstHalf.length).map((e) => e.kind).join(",");
check(
  firstHalf.length === 0 || secondStart !== firstKinds,
  "the continuation does not replay what was already read",
);

// Nothing lost: the run's ending is in the half that arrived after the cut,
// which is the assertion that would have caught the original bug.
const completed = secondHalf.find((e) => e.kind === "complete");
check(!!completed, "the run's `complete` frame arrives on the reattached stream");
if (completed) {
  check(
    completed.status === "done",
    `and the run finished properly (status ${completed.status}, ${completed.stop_reason})`,
  );
}
check(
  secondHalf.some((e) => e.kind === "assistant_node"),
  "the answer is written, so the reply survives a cut stream",
);

console.log(
  `\n${failures.length ? `FAILED — ${failures.length} check(s)` : "ok  a deep run survives losing its stream"}` +
  `  (${firstHalf.length} events before the cut, ${secondHalf.length} after)`,
);
process.exit(failures.length ? 1 : 0);
