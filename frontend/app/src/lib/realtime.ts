// Workspace realtime room client (FR-5). One WebSocket per active workspace:
// presence rosters + live fan-out of teammates' activity (streamed turns on
// shared threads, new conversations/branches, saved prompts).
//
// Design: a module-level connection manager + subscriber list, driven by
// `connectRoom` from the workspace layout. Components subscribe with
// `onRoomEvent` and receive every frame; the presence store is updated here so
// `usePresence` is a plain selector. Reconnects with capped backoff — realtime
// is an overlay, so a dropped socket degrades to "refresh to see changes",
// never an error state.
import { API_BASE } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { usePresenceStore } from "@/store/presence";

export interface RoomUser {
  user_id: string;
  email: string;
  // Branch/conversation this user has open right now (null/absent = idle).
  // Server folds it into every presence frame; the Map and conversation rows
  // draw dots from it.
  viewing?: string | null;
  viewing_conversation?: string | null;
}

export type RoomEvent =
  | { kind: "presence"; workspace_id: string; users: RoomUser[] }
  | {
      kind: "run_event";
      workspace_id: string;
      conversation_id: string;
      branch_id: string;
      author_id: string;
      event: Record<string, any>;
    }
  | { kind: "conversation.created"; workspace_id: string; conversation_id: string; title: string }
  | { kind: "conversation.updated"; workspace_id: string; conversation_id: string; title: string }
  | { kind: "conversation.deleted"; workspace_id: string; conversation_id: string }
  | { kind: "branch.created"; workspace_id: string; conversation_id: string; branch_id: string; name: string }
  | { kind: "branch.updated"; workspace_id: string; conversation_id: string; branch_id: string; name: string }
  | { kind: "branch.deleted"; workspace_id: string; conversation_id: string; branch_id: string }
  | { kind: "messages.deleted"; workspace_id: string; conversation_id: string; branch_id: string; node_ids: string[] }
  | { kind: "references.updated"; workspace_id: string; conversation_id: string }
  | { kind: "prompt.saved"; workspace_id: string; prompt: Record<string, any> }
  | { kind: "prompt.deleted"; workspace_id: string; prompt_id: string }
  | { kind: "pong" };

type Listener = (ev: RoomEvent) => void;

let socket: WebSocket | null = null;
let currentWid: string | null = null;
let retry = 0;
let reconnectTimer: number | null = null;
let pingTimer: number | null = null;
let lastViewing: { branch: string | null; conv: string | null } = { branch: null, conv: null }; // resent after reconnect
const listeners = new Set<Listener>();

/** Tell the room which branch (and conversation) this client is viewing. */
export function sendViewing(branchId: string | null, conversationId: string | null = null) {
  lastViewing = { branch: branchId, conv: conversationId };
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ kind: "viewing", branch_id: branchId, conversation_id: conversationId }));
  }
}

export function onRoomEvent(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function wsUrl(wid: string, token: string): string {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}/ws/workspaces/${wid}?token=${encodeURIComponent(token)}`;
}

function cleanup() {
  if (reconnectTimer !== null) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  if (pingTimer !== null) { clearInterval(pingTimer); pingTimer = null; }
  if (socket) {
    socket.onclose = null; // no reconnect from an intentional close
    socket.close();
    socket = null;
  }
}

function open(wid: string) {
  const token = getToken();
  if (!token) return;
  const ws = new WebSocket(wsUrl(wid, token));
  socket = ws;

  ws.onopen = () => {
    retry = 0;
    usePresenceStore.getState().setLive(true);
    // A reconnect starts with a blank socket info dict server-side: replay
    // what we're viewing so presence stays truthful.
    if (lastViewing.branch) {
      ws.send(JSON.stringify({ kind: "viewing", branch_id: lastViewing.branch, conversation_id: lastViewing.conv }));
    }
    // Keep intermediaries from idling the connection out.
    pingTimer = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 30_000);
  };
  ws.onmessage = (msg) => {
    let ev: RoomEvent;
    try { ev = JSON.parse(msg.data); } catch { return; }
    if (ev.kind === "presence") {
      usePresenceStore.getState().setUsers(ev.users);
    }
    listeners.forEach((fn) => fn(ev));
  };
  ws.onclose = () => {
    if (pingTimer !== null) { clearInterval(pingTimer); pingTimer = null; }
    usePresenceStore.getState().setLive(false);
    if (currentWid !== wid) return; // room changed; a new socket owns things now
    const delay = Math.min(15_000, 500 * 2 ** retry++);
    reconnectTimer = window.setTimeout(() => open(wid), delay);
  };
}

/** Join a workspace room (closing any previous room). */
export function connectRoom(wid: string) {
  if (currentWid === wid && socket && socket.readyState <= WebSocket.OPEN) return;
  disconnectRoom();
  currentWid = wid;
  open(wid);
}

/** Leave the current room (on workspace switch / logout / unmount). */
export function disconnectRoom() {
  currentWid = null;
  retry = 0;
  cleanup();
  usePresenceStore.getState().reset();
}
