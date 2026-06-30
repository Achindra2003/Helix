// Typed REST client. Attaches the JWT (when present) and normalises the
// backend's uniform error shape: { error: { code, message } }.
import { getToken } from "@/lib/auth";
import type {
  AuthResponse, Conversation, ConversationRef, Branch, Node, Prompt, Workspace, Member, Invite, Health, User,
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

// --- conversations (live engine routes are root-level) ---
export const listConversations = (workspaceId: string, viewerId?: string) => {
  const q = new URLSearchParams({ workspace_id: workspaceId });
  if (viewerId) q.set("viewer_id", viewerId);
  return request<{ items: Conversation[] }>(`/conversations?${q.toString()}`);
};
export const getConversation = (cid: string) => request<Conversation>(`/conversations/${cid}`);
export const createConversation = (workspaceId: string, title: string, visibility = "shared", authorId = "u1") =>
  request<{ conversation_id: string; branch_id: string }>("/conversations", {
    method: "POST",
    body: JSON.stringify({ workspace_id: workspaceId, author_id: authorId, title, visibility }),
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
export const exportUrl = (cid: string, branchId: string, format: "md" | "json") =>
  `${API_BASE}/conversations/${cid}/export?format=${format}&branch=${branchId}`;

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

// --- prompts (contract §8) ---
export const listPrompts = (wid: string, q?: string, tag?: string) => {
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (tag) p.set("tag", tag);
  const qs = p.toString();
  return request<{ prompts: Prompt[] }>(`/workspaces/${wid}/prompts${qs ? `?${qs}` : ""}`);
};
export const savePrompt = (wid: string, title: string, body: string, tags: string[], authorId = "u1") =>
  request<Prompt>(`/workspaces/${wid}/prompts`, {
    method: "POST",
    body: JSON.stringify({ author_id: authorId, title, body, tags }),
  });
export const getPrompt = (pid: string) => request<Prompt>(`/prompts/${pid}`);
