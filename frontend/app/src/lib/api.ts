// Typed REST client. Attaches the JWT (when present) and normalises the
// backend's uniform error shape: { error: { code, message } }.
import { getToken } from "@/lib/auth";
import { useSession } from "@/store/session";
import type {
  AuthResponse, Conversation, ConversationRef, Branch, BranchStatus, Node, Prompt, Workspace, Member, Invite, Health, User,
  MapConversation, WorkspaceDocument, DocumentSearchHit, DeepRunSummary, DeepRunRecord,
  WorkspaceSearchHit, WorkspaceUsage, InviteSummary, ToolSettings, Decision, PublicConfig,
  ReasoningMode, ServerNotice,
} from "@/lib/types";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

// Paths where a 401 is a *result* (bad login, wrong current password), not an
// expired session — those must never nuke the session.
const AUTH_RESULT_PATHS = ["/api/auth/", "/api/me/password"];

// Names the address actually being called, rather than the port a developer's
// machine happens to use. "Is the backend running on :8000?" is nonsense to
// someone on a deployed instance — and this is the first thing anyone sees
// when their connection drops.
const unreachable = () =>
  `Cannot reach Helix at ${API_BASE}. It may be offline, or your connection dropped.`;

function sessionExpired() {
  // A hard redirect is deliberate — the app's state is stale beyond repair
  // once the token is dead.
  useSession.getState().logout();
  window.location.assign("/auth");
}

async function request<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(API_BASE + path, { ...opts, headers });
  } catch {
    throw new ApiError(0, "network", unreachable());
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    // The 7-day JWT expiring mid-session: without this, every click just
    // error-toasts until the user thinks to reload. Sign out and start over.
    if (res.status === 401 && token && !AUTH_RESULT_PATHS.some((p) => path.startsWith(p))) {
      sessionExpired();
    }
    const err = data?.error ?? {};
    throw new ApiError(res.status, err.code ?? "error", err.message ?? `HTTP ${res.status}`);
  }
  return data as T;
}

// --- health ---
export const getHealth = () => request<Health>("/health");
// Unauthenticated, and the only call the sign-in screen can make before there
// is a session: it says whether this instance still lets strangers sign up.
export const getPublicConfig = () => request<PublicConfig>("/api/public-config");

// NOTE on prefixes: auth + workspaces/members/invites live under `/api`
// (routers/auth.py, routers/workspaces.py use prefix="/api"); conversations and
// prompts are mounted at the root. Keep these exactly in sync with the backend.

// --- auth (contract §4) ---
// `invite` is only consulted by an invite-only instance, where it is what
// admits the caller. Sent whenever we're holding one, so the same call works
// either way.
export const register = (email: string, password: string, invite?: string | null) =>
  request<AuthResponse>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password, invite }) });
export const login = (email: string, password: string) =>
  request<AuthResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const me = () => request<User>("/api/me");
// Always 202, whether or not the address has an account — the server refuses
// to be an account enumerator, so the UI must not imply an answer either.
export const forgotPassword = (email: string) =>
  request<void>("/api/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
// The token is signed against the user's current password hash, so it stops
// working the moment the reset lands: one link, one use.
export const resetPassword = (token: string, password: string) =>
  request<void>("/api/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, new_password: password }),
  });
export const changePassword = (currentPassword: string, newPassword: string) =>
  request<void>("/api/me/password", {
    method: "PATCH",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
// 409 (owns_workspaces) if the caller still owns a workspace — the server
// refuses to let one account's deletion take a team's workspace with it.
// Takes the password: this is irreversible, and a bearer token lasts a week.
export const deleteAccount = (password: string) =>
  request<void>("/api/me", { method: "DELETE", body: JSON.stringify({ password }) });

// --- workspaces (contract §5) ---
export const listWorkspaces = () => request<Workspace[]>("/api/workspaces");
export const createWorkspace = (name: string) =>
  request<Workspace>("/api/workspaces", { method: "POST", body: JSON.stringify({ name }) });
export const getWorkspace = (wid: string) => request<Workspace>(`/api/workspaces/${wid}`);
export const renameWorkspace = (wid: string, name: string) =>
  request<Workspace>(`/api/workspaces/${wid}`, { method: "PATCH", body: JSON.stringify({ name }) });
// Owner-only; cascades everything in the workspace (conversations, documents,
// runs, invites, settings, memberships) server-side.
export const deleteWorkspace = (wid: string) =>
  request<void>(`/api/workspaces/${wid}`, { method: "DELETE" });
// Any member except the canonical owner (they delete instead).
export const leaveWorkspace = (wid: string) =>
  request<void>(`/api/workspaces/${wid}/leave`, { method: "POST" });
// Semantic search across the workspace's conversation history (server-side
// visibility: shared threads + the caller's own private ones).
export const searchWorkspace = (wid: string, query: string, k = 10) =>
  request<{ items: WorkspaceSearchHit[] }>(`/api/workspaces/${wid}/search`, {
    method: "POST",
    body: JSON.stringify({ query, k }),
  });
export const getWorkspaceUsage = (wid: string) =>
  request<WorkspaceUsage>(`/api/workspaces/${wid}/usage`);
export const listMembers = (wid: string) => request<Member[]>(`/api/workspaces/${wid}/members`);

// --- notices: the bell, server-side so it outlives the tab ---
// Not scoped to a workspace on purpose — being asked something is not less
// urgent because you happen to be looking at a different workspace.
export const listNotices = () => request<{ notices: ServerNotice[] }>("/api/notices");
export const markNoticesRead = () =>
  request<{ ok: boolean }>("/api/notices/read", { method: "POST" });
export const setMemberRole = (wid: string, uid: string, role: string) =>
  request<Member>(`/api/workspaces/${wid}/members/${uid}`, { method: "PATCH", body: JSON.stringify({ role }) });
// Kick (owner-only) — the counterpart of voluntary leave.
export const removeMember = (wid: string, uid: string) =>
  request<void>(`/api/workspaces/${wid}/members/${uid}`, { method: "DELETE" });
export const createInvite = (wid: string, role = "collaborator") =>
  request<Invite>(`/api/workspaces/${wid}/invites`, { method: "POST", body: JSON.stringify({ role }) });
export const listInvites = (wid: string) =>
  request<{ items: InviteSummary[] }>(`/api/workspaces/${wid}/invites`);
export const revokeInvite = (wid: string, token: string) =>
  request<void>(`/api/workspaces/${wid}/invites/${token}`, { method: "DELETE" });
export const previewInvite = (token: string) =>
  request<{ workspace_name: string }>(`/api/invites/${token}`);
export const acceptInvite = (token: string) =>
  request<Workspace>(`/api/invites/${token}/accept`, { method: "POST" });

// --- per-workspace provider settings (BYO key) ---
// The API key is write-only: it goes up in PUT, never comes back down (owners
// see a masked form at most). `configured` is the composer's "am I alive?" bit.
export type ProviderSettings = {
  provider: string;
  chat_model: string;
  deep_model: string;
  effective_provider: string;
  effective_chat_model: string;
  effective_deep_model: string;
  source: "workspace" | "server";
  configured: boolean;
  deep_available: boolean;
  base_url?: string; // owner-only
  api_key_masked?: string; // owner-only
};
export const getProviderSettings = (wid: string) =>
  request<ProviderSettings>(`/api/workspaces/${wid}/settings/provider`);
export const putProviderSettings = (
  wid: string,
  body: { provider: string; api_key?: string; base_url?: string; chat_model?: string; deep_model?: string },
) =>
  request<ProviderSettings>(`/api/workspaces/${wid}/settings/provider`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
// With `candidate`, the server tests those values without storing them — so a
// wrong key is caught before it becomes the workspace's live configuration.
// Omit `api_key` inside the candidate to test against the already-stored key.
export const testProviderSettings = (
  wid: string,
  candidate?: { provider: string; api_key?: string; base_url: string; chat_model: string; deep_model: string },
) =>
  request<{ ok: boolean; detail: string }>(`/api/workspaces/${wid}/settings/provider/test`, {
    method: "POST",
    body: candidate ? JSON.stringify(candidate) : undefined,
  });

// --- agent tool allowlist (FR-14) ---
// Read: any member (the composer needs to know what agent runs can do).
// Write: owner-only. An empty list is a valid choice (a tool-less agent),
// distinct from never-configured (the safe workspace-internal default).
export const getToolSettings = (wid: string) =>
  request<ToolSettings>(`/api/workspaces/${wid}/settings/tools`);
export const putToolSettings = (wid: string, allowed: string[]) =>
  request<ToolSettings>(`/api/workspaces/${wid}/settings/tools`, {
    method: "PUT",
    body: JSON.stringify({ allowed }),
  });

// --- conversations (live engine routes are root-level) ---
// Identity (viewer/author) is derived server-side from the JWT — never sent.
export const listConversations = (workspaceId: string) => {
  const q = new URLSearchParams({ workspace_id: workspaceId });
  return request<{ items: Conversation[] }>(`/conversations?${q.toString()}`);
};
export const getConversation = (cid: string) => request<Conversation>(`/conversations/${cid}`);
// Rename/delete a conversation — its author, or a workspace owner.
export const renameConversation = (cid: string, title: string) =>
  request<{ conversation_id: string; title: string }>(`/conversations/${cid}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
export const deleteConversation = (cid: string) =>
  request<{ removed_nodes: number }>(`/conversations/${cid}`, { method: "DELETE" });
// Rename/delete a fork branch (Collaborator+; main and forked-from refuse).
export const renameBranch = (bid: string, name: string) =>
  request<{ branch_id: string; name: string }>(`/conversations/branches/${bid}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
export const deleteBranch = (bid: string) =>
  request<{ removed_nodes: number }>(`/conversations/branches/${bid}`, { method: "DELETE" });
export const createConversation = (workspaceId: string, title: string, visibility = "shared") =>
  request<{ conversation_id: string; branch_id: string }>("/conversations", {
    method: "POST",
    body: JSON.stringify({ workspace_id: workspaceId, title, visibility }),
  });
export const listBranches = (cid: string) =>
  request<{ items: Branch[] }>(`/conversations/${cid}/branches`);
export const getHistory = (branchId: string) =>
  request<{ branch_id: string; nodes: Node[] }>(`/conversations/branches/${branchId}/history`);
// Remove the branch's trailing turn you authored (user message + its reply, if
// one landed). 403 if you're not the author; 409 once a branch has forked from
// it — append-only history stays intact for anyone who already branched off.
export const deleteLastMessage = (branchId: string) =>
  request<{ removed_ids: string[] }>(`/conversations/${branchId}/messages/last`, { method: "DELETE" });
export const forkBranch = (cid: string, fromNodeId: string, name: string, intent = "") =>
  request<{ branch_id: string; fork_node_id: string; name: string; intent: string }>(`/conversations/${cid}/fork`, {
    method: "POST",
    body: JSON.stringify({ from_node_id: fromNodeId, name, intent }),
  });
// Record what came of an exploration. `status: "open"` reopens it and clears
// the verdict. The server requires a reason for adopted/abandoned — a verdict
// without one is not a record.
export const resolveBranch = (bid: string, status: BranchStatus, resolution: string) =>
  request<Branch>(`/conversations/branches/${bid}/resolve`, {
    method: "POST",
    body: JSON.stringify({ status, resolution }),
  });
// Back an exploration, or withdraw backing — toggles, and returns the tally.
// Approval voting: backing one branch says nothing about its siblings.
export const voteBranch = (bid: string) =>
  request<{ branch_id: string; backing: boolean; votes: string[] }>(
    `/conversations/branches/${bid}/vote`,
    { method: "POST" },
  );
// Export is auth-gated, so a plain <a href> can't carry the JWT: fetch with the
// token and hand the payload to the browser as a blob download. The server
// names the file (Content-Disposition); the fallback only covers a proxy that
// strips the header.
const downloadFile = async (path: string, fallback: string) => {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, "export_failed", `Export failed (HTTP ${res.status})`);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallback;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

/** One branch, root to head: the fair copy of a single path. */
export const downloadExport = (cid: string, branchId: string, format: "md" | "json") =>
  downloadFile(
    `/conversations/${cid}/export?format=${format}&branch=${branchId}`,
    `conversation.${format}`,
  );

/** The whole conversation as a decision report — every exploration, including
 *  the abandoned ones, with its verdict and reason. Omitting `branch` is what
 *  asks for the report rather than a transcript. */
export const downloadReport = (cid: string, format: "md" | "json") =>
  downloadFile(`/conversations/${cid}/export?format=${format}`, `report.${format}`);

/** Every decision in the workspace, gathered — the ledger as a document. */
export const downloadWorkspaceReport = (wid: string, format: "md" | "json") =>
  downloadFile(`/workspaces/${wid}/export?format=${format}`, `decisions.${format}`);

// The five reasoning presets and which one an unspecified run gets. Describes
// the build, not a workspace, so it's fetched once and shared.
export const getReasoningModes = () =>
  request<{ default: string; modes: ReasoningMode[] }>("/conversations/deep/modes");

// --- deep-run control (AI-LANE-CONTRACTS §2.2): the run outlives the tab ---
export type DeepRunStatus = {
  run_id: string;
  status: "queued" | "running" | "paused" | "done" | "error" | "killed";
  seq: number;
  queue_position: number | null;
};
export const getDeepRunStatus = (runId: string) =>
  request<DeepRunStatus>(`/conversations/deep/runs/${runId}/status`);
// Closing the SSE no longer stops a run — this does (cooperative).
export const killDeepRun = (runId: string) =>
  request<{ run_id: string; status: string }>(`/conversations/deep/runs/${runId}/kill`, { method: "POST" });

// --- the team's reasoning archive: persisted deep-run records ---
export const listDeepRuns = (cid: string) =>
  request<{ items: DeepRunSummary[] }>(`/conversations/${cid}/deep/runs`);
export const getDeepRunRecord = (runId: string) =>
  request<DeepRunRecord>(`/conversations/deep/runs/${runId}/record`);

// --- workspace map (the whole reasoning graph in one read) ---
export const getWorkspaceMap = (wid: string) =>
  request<{ conversations: MapConversation[] }>(`/workspaces/${wid}/map`);
// Every verdict the caller may see, newest first — the catch-up surface for
// "what did the team decide, and why".
export const listDecisions = (wid: string) =>
  request<{ items: Decision[] }>(`/workspaces/${wid}/decisions`);

// What the thread concluded. An empty string reopens the question.
// Say something to your teammates in the thread. It keeps its place in the
// history and is never shown to the model — coordination is not a prompt.
export const postNote = (branchId: string, content: string) =>
  request<Node>(`/conversations/${branchId}/notes`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
export const concludeConversation = (cid: string, conclusion: string) =>
  request<Conversation>(`/conversations/${cid}/conclude`, {
    method: "POST",
    body: JSON.stringify({ conclusion }),
  });

// --- cross-conversation references (link another shared thread as live context) ---
export const listReferences = (cid: string) =>
  request<{ items: ConversationRef[] }>(`/conversations/${cid}/references`);
export const addReference = (cid: string, referencedConversationId: string) =>
  request<{ items: ConversationRef[] }>(`/conversations/${cid}/references`, {
    method: "POST",
    body: JSON.stringify({ referenced_conversation_id: referencedConversationId }),
  });
export const removeReference = (cid: string, referencedConversationId: string) =>
  request<{ items: ConversationRef[] }>(
    `/conversations/${cid}/references/${referencedConversationId}`,
    { method: "DELETE" },
  );

// --- workspace documents: the knowledge base (AI-LANE-CONTRACTS §2.3) ---
// Upload is multipart (the one non-JSON call): the browser sets the boundary
// header itself, so this bypasses request() and its forced Content-Type.
export const uploadDocument = async (wid: string, file: File): Promise<WorkspaceDocument> => {
  const token = getToken();
  const form = new FormData();
  form.append("file", file);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/workspaces/${wid}/documents`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
  } catch {
    throw new ApiError(0, "network", unreachable());
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const err = data?.error ?? {};
    throw new ApiError(res.status, err.code ?? "error", err.message ?? `HTTP ${res.status}`);
  }
  return data as WorkspaceDocument;
};
export const listDocuments = (wid: string) =>
  request<{ items: WorkspaceDocument[] }>(`/api/workspaces/${wid}/documents`);
export const getDocument = (wid: string, id: string) =>
  request<WorkspaceDocument>(`/api/workspaces/${wid}/documents/${id}`);
export const deleteDocument = (wid: string, id: string) =>
  request<{ ok: boolean }>(`/api/workspaces/${wid}/documents/${id}`, { method: "DELETE" });
// Give a source its bibliographic identity, so a citation reads "Smith et al.
// (2019)" rather than naming a file on somebody's laptop. Any collaborator —
// cataloguing is work a second person does well.
export const updateDocumentMetadata = (
  wid: string,
  id: string,
  body: { doc_title?: string; authors?: string; year?: string; identifier?: string },
) =>
  request<WorkspaceDocument>(`/api/workspaces/${wid}/documents/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
export const searchDocuments = (wid: string, query: string, k = 6) =>
  request<{ items: DocumentSearchHit[] }>(`/api/workspaces/${wid}/documents/search`, {
    method: "POST",
    body: JSON.stringify({ query, k }),
  });

// --- prompts (contract §8) ---
export const listPrompts = (wid: string, q?: string, tag?: string) => {
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (tag) p.set("tag", tag);
  const qs = p.toString();
  return request<{ prompts: Prompt[] }>(`/workspaces/${wid}/prompts${qs ? `?${qs}` : ""}`);
};
export const savePrompt = (wid: string, title: string, body: string, tags: string[]) =>
  request<Prompt>(`/workspaces/${wid}/prompts`, {
    method: "POST",
    body: JSON.stringify({ title, body, tags }),
  });
export const getPrompt = (pid: string) => request<Prompt>(`/prompts/${pid}`);
// Edit/delete a saved prompt — its author, or a workspace owner.
export const updatePrompt = (pid: string, title: string, body: string, tags: string[]) =>
  request<Prompt>(`/prompts/${pid}`, { method: "PATCH", body: JSON.stringify({ title, body, tags }) });
export const deletePrompt = (pid: string) =>
  request<{ ok: boolean }>(`/prompts/${pid}`, { method: "DELETE" });
