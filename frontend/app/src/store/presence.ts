// Who is in the workspace room right now. Written by lib/realtime.ts; read by
// usePresence / the presence bar. `live` distinguishes a real roster from the
// offline fallback ("just you") so the UI can label the difference honestly.
import { create } from "zustand";
import type { RoomUser } from "@/lib/realtime";

interface PresenceState {
  users: RoomUser[];
  live: boolean;
  setUsers: (users: RoomUser[]) => void;
  setLive: (live: boolean) => void;
  reset: () => void;
}

export const usePresenceStore = create<PresenceState>((set) => ({
  users: [],
  live: false,
  setUsers: (users) => set({ users }),
  setLive: (live) => set((s) => (live ? { live } : { live, users: [] })),
  reset: () => set({ users: [], live: false }),
}));
