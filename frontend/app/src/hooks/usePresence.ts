// Presence seam. The WebSocket room (contract §11) isn't built yet, so today this
// returns "you, online". When the WS lands, swap the body to subscribe to the room
// and the whole presence UI lights up with no component changes.
import { useSession } from "@/store/session";

export interface Presence {
  user_id: string;
  email: string;
  online: boolean;
}

export function usePresence(_workspaceId: string | null): { members: Presence[]; live: boolean } {
  const user = useSession((s) => s.user);
  const members: Presence[] = user ? [{ user_id: user.id, email: user.email, online: true }] : [];
  return { members, live: false };
}
