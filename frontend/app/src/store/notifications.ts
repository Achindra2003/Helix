// Session-scoped notification center. Fed by the workspace room's WS events
// (shell-level listener in WorkspaceLayout) and by your own deep-run
// completions (ChatView's SSE handler). Deliberately in-memory only: it covers
// "I was on another tab/conversation", not "I closed the browser for a day" —
// missed-event persistence is a documented non-goal of this pass.
import { create } from "zustand";

export interface Notice {
  id: string;
  text: string;
  conversationId?: string;
  time: string; // display time (HH:MM)
  read: boolean;
}

const CAP = 50;

interface NotificationStore {
  items: Notice[];
  add: (n: Omit<Notice, "id" | "read" | "time">) => void;
  markAllRead: () => void;
  clear: () => void;
}

export const useNotifications = create<NotificationStore>((set) => ({
  items: [],
  add: (n) =>
    set((st) => ({
      items: [
        {
          ...n,
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          read: false,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
        ...st.items,
      ].slice(0, CAP),
    })),
  markAllRead: () => set((st) => ({ items: st.items.map((i) => ({ ...i, read: true })) })),
  clear: () => set({ items: [] }),
}));

export const useUnreadCount = () =>
  useNotifications((st) => st.items.filter((i) => !i.read).length);
