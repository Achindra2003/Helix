// RBAC — policy as data (contract §2). The default seed matrix; the client uses
// it to hide/disable controls. The server is the real enforcer (once gated).
import type { Role } from "@/lib/types";

export type Action =
  | "conversation.read"
  | "message.send"
  | "branch.fork"
  | "prompt.write"
  | "document.write" // upload / delete-own (owner deletes any)
  | "run.escalate"
  | "run.control" // steer / kill
  | "member.manage"
  | "workspace.manage" // rename / delete the workspace itself
  | "permission.edit";

const MATRIX: Record<Action, Record<Role, boolean>> = {
  "conversation.read": { owner: true, collaborator: true, observer: true },
  "message.send": { owner: true, collaborator: true, observer: false },
  "branch.fork": { owner: true, collaborator: true, observer: false },
  "prompt.write": { owner: true, collaborator: true, observer: false },
  "document.write": { owner: true, collaborator: true, observer: false },
  "run.escalate": { owner: true, collaborator: true, observer: false },
  "run.control": { owner: true, collaborator: true, observer: false },
  "member.manage": { owner: true, collaborator: false, observer: false },
  "workspace.manage": { owner: true, collaborator: false, observer: false },
  "permission.edit": { owner: true, collaborator: false, observer: false },
};

export function can(role: Role, action: Action): boolean {
  return MATRIX[action]?.[role] ?? false;
}

export const PERMISSION_ROWS: { key: string; action: Action }[] = [
  { key: "conversation.read / replay", action: "conversation.read" },
  { key: "message.send", action: "message.send" },
  { key: "branch.fork", action: "branch.fork" },
  { key: "prompt.write", action: "prompt.write" },
  { key: "document.upload / delete", action: "document.write" },
  { key: "run.escalate", action: "run.escalate" },
  { key: "run.steer / run.kill", action: "run.control" },
  { key: "member.invite / role", action: "member.manage" },
  { key: "workspace.rename / delete", action: "workspace.manage" },
  { key: "permission.edit", action: "permission.edit" },
];

export const ROLE_META: Record<Role, { sigil: string; label: string }> = {
  owner: { sigil: "♔", label: "Owner" },
  collaborator: { sigil: "⌇", label: "Collaborator" },
  observer: { sigil: "◉", label: "Observer" },
};
