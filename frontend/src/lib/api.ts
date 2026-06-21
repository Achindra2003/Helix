// Typed client for the Helix API. Mirrors helix-api-contract.md.
const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

let authToken: string | null = null;
export function setToken(t: string | null) {
  authToken = t;
}

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(message: string, code: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

type ReqOpts = { method?: string; body?: unknown; auth?: boolean };

async function req<T>(path: string, opts: ReqOpts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.auth !== false && authToken)
    headers["Authorization"] = `Bearer ${authToken}`;

  const res = await fetch(`${BASE}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err = data?.error ?? {};
    throw new ApiError(
      err.message ?? `Request failed (${res.status})`,
      err.code ?? "error",
      res.status
    );
  }
  return data as T;
}

// ─── Types (wire shapes) ───────────────────────────────────────────────
export interface User {
  id: string;
  email: string;
  created_at?: string;
}
export interface AuthResponse {
  user: User;
  token: string;
}
export interface Workspace {
  id: string;
  name: string;
  owner_id: string;
  role: "owner" | "collaborator" | "observer";
  created_at: string;
}
export interface Member {
  user_id: string;
  email: string;
  role: string;
  joined_at: string;
}
export interface InviteOut {
  token: string;
  url: string;
  expires_at: string;
}
export interface InvitePreview {
  workspace_name: string;
}
export interface Health {
  status: string;
  db_time: string;
  provider: string;
}

// ─── Endpoints ─────────────────────────────────────────────────────────
export const api = {
  health: () => req<Health>("/health", { auth: false }),

  register: (email: string, password: string) =>
    req<AuthResponse>("/api/auth/register", {
      method: "POST",
      body: { email, password },
      auth: false,
    }),
  login: (email: string, password: string) =>
    req<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    }),
  me: () => req<User>("/api/me"),

  listWorkspaces: () => req<Workspace[]>("/api/workspaces"),
  createWorkspace: (name: string) =>
    req<Workspace>("/api/workspaces", { method: "POST", body: { name } }),
  getWorkspace: (id: string) => req<Workspace>(`/api/workspaces/${id}`),
  listMembers: (id: string) => req<Member[]>(`/api/workspaces/${id}/members`),
  createInvite: (id: string) =>
    req<InviteOut>(`/api/workspaces/${id}/invites`, { method: "POST" }),

  previewInvite: (token: string) =>
    req<InvitePreview>(`/api/invites/${token}`, { auth: false }),
  acceptInvite: (token: string) =>
    req<Workspace>(`/api/invites/${token}/accept`, { method: "POST" }),
};

/**
 * Stream a chat reply (SSE). Calls `onToken` per chunk. POST, so we read the
 * body manually rather than using EventSource (GET-only).
 */
export async function streamChat(
  prompt: string,
  onToken: (chunk: string) => void
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!res.body) throw new Error("no response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.replace(/^data: /, "");
      if (line === "[DONE]") return;
      onToken(line);
    }
  }
}
