// RBAC — policy as data (contract §2). The default seed matrix; the client uses
// it to hide/disable controls. The server is the real enforcer (once gated).
import type { Role } from "@/lib/types";
import { ROLE_SIGIL } from "@/lib/glyphs";

export type Action =
  | "conversation.read"
  | "message.send"
  | "note.write" // say it to the room, not to the model — the Observer's one write
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
  // The one row where an Observer is true. A note never reaches the model, so
  // it cannot change a reply, spend the budget, or alter the thread's lineage —
  // it only addresses the humans. An Observer who cannot say "that citation is
  // wrong" is a decorative role, and this is the smallest fix that isn't a
  // fourth role.
  "note.write": { owner: true, collaborator: true, observer: true },
  "branch.fork": { owner: true, collaborator: true, observer: false },
  "prompt.write": { owner: true, collaborator: true, observer: false },
  "document.write": { owner: true, collaborator: true, observer: false },
  "run.escalate": { owner: true, collaborator: true, observer: false },
  "run.control": { owner: true, collaborator: true, observer: false },
  "member.manage": { owner: true, collaborator: false, observer: false },
  "workspace.manage": { owner: true, collaborator: false, observer: false },
  "permission.edit": { owner: true, collaborator: false, observer: false },
};

// Mirrors the server's ROLE_RANK (api/models.py). Used to clamp role preview:
// the client may never rank itself above what the server recorded.
export const ROLE_RANK: Record<Role, number> = { observer: 0, collaborator: 1, owner: 2 };

export function can(role: Role, action: Action): boolean {
  return MATRIX[action]?.[role] ?? false;
}

export const PERMISSION_ROWS: { key: string; action: Action }[] = [
  { key: "conversation.read / replay", action: "conversation.read" },
  { key: "message.send", action: "message.send" },
  { key: "note.write (to the team)", action: "note.write" },
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
  owner: { sigil: ROLE_SIGIL.owner, label: "Owner" },
  collaborator: { sigil: ROLE_SIGIL.collaborator, label: "Collaborator" },
  observer: { sigil: ROLE_SIGIL.observer, label: "Observer" },
};
