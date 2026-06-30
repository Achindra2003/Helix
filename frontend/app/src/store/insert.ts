// Cross-route hand-off: the Library's "Insert →" stashes a prompt id, navigates to
// Chat, and ChatView consumes it to run the prompt as a turn on the active branch.
import { create } from "zustand";

interface InsertStore {
  promptId: string | null;
  request: (id: string) => void;
  clear: () => void;
}

export const usePendingInsert = create<InsertStore>((set) => ({
  promptId: null,
  request: (promptId) => set({ promptId }),
  clear: () => set({ promptId: null }),
}));
