// Session-scoped unread markers for conversation rows. Fed by the shell-level
// room listener (a teammate's turn landing in a thread you're not reading),
// cleared the moment you open the thread. Like the notification bell, this is
// deliberately in-memory: it answers "what moved while I was here", not "what
// happened since last week".
import { create } from "zustand";

interface UnreadStore {
  ids: Record<string, true>;
  mark: (conversationId: string) => void;
  clear: (conversationId: string) => void;
  reset: () => void;
}

export const useUnread = create<UnreadStore>((set) => ({
  ids: {},
  mark: (id) => set((st) => (st.ids[id] ? st : { ids: { ...st.ids, [id]: true } })),
  clear: (id) =>
    set((st) => {
      if (!st.ids[id]) return st;
      const next = { ...st.ids };
      delete next[id];
      return { ids: next };
    }),
  reset: () => set({ ids: {} }),
}));
