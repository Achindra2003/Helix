// Global session: the authenticated user, the active workspace, and the
// role-preview (lets you view the workspace as each role — a product/demo feature
// distinct from your real role).
import { create } from "zustand";
import type { Role, User, Workspace } from "@/lib/types";
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
    if (s.rolePreview) return s.rolePreview;
    const ws = s.workspaces.find((w) => w.id === s.activeWorkspaceId);
    return ws?.role ?? "owner";
  });
}

export function useActiveWorkspace(): Workspace | null {
  return useSession((s) => s.workspaces.find((w) => w.id === s.activeWorkspaceId) ?? null);
}
