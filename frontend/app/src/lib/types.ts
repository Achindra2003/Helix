// API DTOs — mirror the FastAPI backend (helix-api-contract.md + live routes).

export type Role = "owner" | "collaborator" | "observer";
export type Visibility = "shared" | "private";

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
  role: Role;
  created_at?: string;
}

export interface Member {
  user_id: string;
  email: string;
  role: Role;
  joined_at?: string;
}

export interface Invite {
  token: string;
  url: string;
  expires_at: string;
}

export interface Conversation {
  id: string;
  workspace_id: string;
  author_id: string;
  title: string;
  visibility: Visibility;
  default_branch_id: string;
  created_at?: string;
}

// A conversation linked in as live cross-thread context (see addReference).
export interface ConversationRef {
  id: string;
  title: string;
}

export interface Branch {
  id: string;
  conversation_id: string;
  name: string;
  parent_branch_id: string | null;
  fork_node_id: string | null;
  head_node_id: string | null;
}

export interface Node {
  id: string;
  branch_id: string;
  parent_id: string | null;
  seq: number;
  role: "user" | "assistant" | "system";
  content: string;
  author_id: string | null;
  token_count: number;
}

export interface Prompt {
  id: string;
  workspace_id: string;
  author_id: string;
  title: string;
  body: string;
  tags: string[];
}

export interface Health {
  status: string;
  db_time: string;
  provider: string;
}

// --- SSE event frames (the engine's run contract; `kind` tags the type) ---
export type RunEvent =
  | { kind: "user_node"; node: Node }
  | { kind: "token"; text: string }
  | { kind: "assistant_node"; node: Node }
  | { kind: "step"; idx: number; node: string; depth: number; energy: number; payload: Record<string, unknown> }
  | { kind: "budget"; tokens_used: number; tokens_budget: number; pct: number }
  | { kind: "waiting"; reason: string }
  | { kind: "complete"; stop_reason: string; status: "done" | "killed" | "error" }
  | { kind: "done" };
