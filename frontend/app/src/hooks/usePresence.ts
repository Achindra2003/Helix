// Presence, live from the workspace WebSocket room (contract §11).
// The room connection is owned by WorkspaceLayout (lib/realtime.ts); this hook
// just selects the roster. When the socket is down we degrade to "you, offline"
// so the presence UI never lies about who's really here.
import { usePresenceStore } from "@/store/presence";
import { useSession } from "@/store/session";

export interface Presence {
  user_id: string;
  email: string;
  online: boolean;
}

export function usePresence(_workspaceId: string | null): { members: Presence[]; live: boolean } {
  const user = useSession((s) => s.user);
  const users = usePresenceStore((s) => s.users);
  const live = usePresenceStore((s) => s.live);

  if (live && users.length > 0) {
    return {
      members: users.map((u) => ({ user_id: u.user_id, email: u.email, online: true })),
      live: true,
    };
  }
  const members: Presence[] = user ? [{ user_id: user.id, email: user.email, online: true }] : [];
  return { members, live: false };
}
