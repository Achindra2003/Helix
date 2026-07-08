// Typed REST client. Attaches the JWT (when present) and normalises the
// backend's uniform error shape: { error: { code, message } }.
import { getToken } from "@/lib/auth";
import type {
  AuthResponse, Conversation, ConversationRef, Branch, Node, Prompt, Workspace, Member, Invite, Health, User,
  MapConversation, WorkspaceDocument, DocumentSearchHit,
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
    throw new ApiError(0, "network", "Cannot reach the Helix API. Is the backend running on :8000?");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const err = data?.error ?? {};
    throw new ApiError(res.status, err.code ?? "error", err.message ?? `HTTP ${res.status}`);
  }
  return data as T;
}

// --- health ---
export const getHealth = () => request<Health>("/health");

// NOTE on prefixes: auth + workspaces/members/invites live under `/api`
// (routers/auth.py, routers/workspaces.py use prefix="/api"); conversations and
// prompts are mounted at the root. Keep these exactly in sync with the backend.

// --- auth (contract §4) ---
export const register = (email: string, password: string) =>
  request<AuthResponse>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password }) });
export const login = (email: string, password: string) =>
  request<AuthResponse>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const me = () => request<User>("/api/me");

// --- workspaces (contract §5) ---
export const listWorkspaces = () => request<Workspace[]>("/api/workspaces");
export const createWorkspace = (name: string) =>
  request<Workspace>("/api/workspaces", { method: "POST", body: JSON.stringify({ name }) });
export const getWorkspace = (wid: string) => request<Workspace>(`/api/workspaces/${wid}`);
export const listMembers = (wid: string) => request<Member[]>(`/api/workspaces/${wid}/members`);
export const setMemberRole = (wid: string, uid: string, role: string) =>
  request<Member>(`/api/workspaces/${wid}/members/${uid}`, { method: "PATCH", body: JSON.stringify({ role }) });
export const createInvite = (wid: string, role = "collaborator") =>
  request<Invite>(`/api/workspaces/${wid}/invites`, { method: "POST", body: JSON.stringify({ role }) });
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
export const testProviderSettings = (wid: string) =>
  request<{ ok: boolean; detail: string }>(`/api/workspaces/${wid}/settings/provider/test`, {
    method: "POST",
  });

// --- conversations (live engine routes are root-level) ---
// Identity (viewer/author) is derived server-side from the JWT — never sent.
export const listConversations = (workspaceId: string) => {
  const q = new URLSearchParams({ workspace_id: workspaceId });
  return request<{ items: Conversation[] }>(`/conversations?${q.toString()}`);
};
export const getConversation = (cid: string) => request<Conversation>(`/conversations/${cid}`);
export const createConversation = (workspaceId: string, title: string, visibility = "shared") =>
  request<{ conversation_id: string; branch_id: string }>("/conversations", {
    method: "POST",
    body: JSON.stringify({ workspace_id: workspaceId, title, visibility }),
  });
export const listBranches = (cid: string) =>
  request<{ items: Branch[] }>(`/conversations/${cid}/branches`);
export const getHistory = (branchId: string) =>
  request<{ branch_id: string; nodes: Node[] }>(`/conversations/branches/${branchId}/history`);
export const forkBranch = (cid: string, fromNodeId: string, name: string) =>
  request<{ branch_id: string; fork_node_id: string; name: string }>(`/conversations/${cid}/fork`, {
    method: "POST",
    body: JSON.stringify({ from_node_id: fromNodeId, name }),
  });
// Export is auth-gated, so a plain <a href> can't carry the JWT: fetch with the
// token and hand the payload to the browser as a blob download.
export const downloadExport = async (cid: string, branchId: string, format: "md" | "json") => {
  const token = getToken();
  const res = await fetch(
    `${API_BASE}/conversations/${cid}/export?format=${format}&branch=${branchId}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!res.ok) throw new ApiError(res.status, "export_failed", `Export failed (HTTP ${res.status})`);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `conversation.${format}`;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

// --- workspace map (the whole reasoning graph in one read) ---
export const getWorkspaceMap = (wid: string) =>
  request<{ conversations: MapConversation[] }>(`/workspaces/${wid}/map`);

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
    throw new ApiError(0, "network", "Cannot reach the Helix API. Is the backend running on :8000?");
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
