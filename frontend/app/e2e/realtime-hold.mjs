// Does the workspace's realtime socket stay open on a deployment?
//
//   node e2e/realtime-hold.mjs [baseUrl] [seconds]
//   node e2e/realtime-hold.mjs https://achindra2003--helix-serve.modal.run 60
//
// `rooms.mjs` asserts over HTTP and never opens a socket, so a host that
// serves every request correctly and silently drops WebSockets passes it
// clean. That is exactly what Modal's `web_server` proxy did: the socket
// opened and closed again inside two seconds, while the identical build held
// it open locally. Nothing in the suite noticed, and presence — the thing that
// makes the workspace feel shared — was gone.
//
// So this is the check that decides a hosting choice, and it belongs next to
// the rooms rather than in somebody's scratch directory. A pass is a socket
// that accepts the presence frame on connect and answers `ping` with `pong`
// for the whole hold.
const API = process.argv[2] || process.env.HELIX_E2E_API || "http://127.0.0.1:8000";
const HOLD_S = Number(process.argv[3] || 60);

const api = async (path, opts = {}) => {
  const res = await fetch(API + path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status} ${(await res.text()).slice(0, 200)}`);
  return res.json();
};

// A throwaway account: the socket is gated on membership, so the probe needs a
// workspace it genuinely belongs to rather than a token alone.
const auth = await api("/api/auth/register", {
  method: "POST",
  body: {
    email: `realtime+${Date.now().toString(36)}@rooms.helix.team`,
    password: "demo-password-1",
  },
});
const workspace = await api("/api/workspaces", {
  method: "POST",
  token: auth.token,
  body: { name: "Realtime hold" },
});

const url =
  `${API.replace(/^https/, "wss").replace(/^http:/, "ws:")}` +
  `/ws/workspaces/${workspace.id}?token=${auth.token}`;

const socket = new WebSocket(url);
const started = Date.now();
const at = () => `${((Date.now() - started) / 1000).toFixed(1)}s`;
let presence = 0;
let pongs = 0;

socket.addEventListener("open", () => console.log(`  open at ${at()}`));
socket.addEventListener("message", (event) => {
  let kind = "?";
  try { kind = JSON.parse(event.data).kind; } catch { /* not our frame */ }
  if (kind === "presence") presence++;
  if (kind === "pong") pongs++;
  console.log(`  ${at()}  ${kind}`);
});
socket.addEventListener("close", (event) => {
  console.log(`\nFAILED: closed at ${at()} (code ${event.code}, clean=${event.wasClean})`);
  console.log("The host is not carrying WebSockets. Presence and live fan-out are dead there.");
  process.exit(1);
});

// The real client pings on a timer (src/lib/realtime.ts). Without it this
// would measure an idle timeout rather than whether the socket survives.
const ping = setInterval(() => {
  if (socket.readyState === WebSocket.OPEN) socket.send("ping");
}, 10_000);

console.log(`holding a socket against ${API} for ${HOLD_S}s`);
setTimeout(() => {
  clearInterval(ping);
  const ok = socket.readyState === WebSocket.OPEN && presence > 0 && pongs > 0;
  console.log(
    `\n${ok ? "ok" : "FAILED"}  held ${HOLD_S}s — ${presence} presence frame(s), ${pongs} pong(s)`,
  );
  socket.close();
  process.exit(ok ? 0 : 1);
}, HOLD_S * 1000);
