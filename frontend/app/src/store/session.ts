// Global session: the authenticated user, the active workspace, and the
// role-preview (lets you view the workspace as each role — a product/demo feature
// distinct from your real role).
import { create } from "zustand";
import type { Role, User, Workspace } from "@/lib/types";
import { ROLE_RANK } from "@/lib/rbac";
import { setToken } from "@/lib/auth";

interface SessionState {
  user: User | null;
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  rolePreview: Role | null; // null = use real role
  setSession: (user: User, token: string) => void;
  setWorkspaces: (ws: Workspace[]) => void;
  setActiveWorkspace: (id: string | null) => void;
  setRolePreview: (r: Role | null) => void;
  logout: () => void;
}

export const useSession = create<SessionState>((set) => ({
  user: null,
  workspaces: [],
  activeWorkspaceId: null,
  rolePreview: null,
  setSession: (user, token) => {
    setToken(token);
    set({ user });
  },
  setWorkspaces: (workspaces) => set({ workspaces }),
  setActiveWorkspace: (activeWorkspaceId) => set({ activeWorkspaceId, rolePreview: null }),
  setRolePreview: (rolePreview) => set({ rolePreview }),
  logout: () => {
    setToken(null);
    set({ user: null, workspaces: [], activeWorkspaceId: null, rolePreview: null });
  },
}));

// The role used to render the UI: preview override, else the active workspace role.
export function useEffectiveRole(): Role {
  return useSession((s) => {
    const ws = s.workspaces.find((w) => w.id === s.activeWorkspaceId);
    // Role preview may only ever REDUCE privilege. Looking at the workspace as
    // an Observer is the feature; ranking yourself up to Owner was a bug that
    // painted owner-only controls — Invite, Delete workspace, Provider settings
    // — for people the server then refused. A preview above your real role is
    // clamped back down to it.
    //
    // Fail closed. A workspace missing from the list means "we don't know yet"
    // — during boot, or right after accepting an invite — and answering "owner"
    // there paints the full owner UI for someone who may be an Observer, who
    // then collects 403s from controls they should never have been shown.
    // Least privilege is also the safe direction for the flicker: controls
    // appear once the list lands, rather than vanishing after an error.
    const real: Role = ws?.role ?? "observer";
    if (s.rolePreview && ROLE_RANK[s.rolePreview] < ROLE_RANK[real]) return s.rolePreview;
    return real;
  });
}

export function useActiveWorkspace(): Workspace | null {
  return useSession((s) => s.workspaces.find((w) => w.id === s.activeWorkspaceId) ?? null);
}
