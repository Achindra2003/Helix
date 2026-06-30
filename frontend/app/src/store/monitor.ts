// Deep Reasoning run state for the monitor panel.
import { create } from "zustand";

export interface TraceStep {
  kind: string; // langgraph node: reason/reflect/synthesize/breathe/surface/steer
  meta: string;
  text: string;
}

export type RunStatus = "idle" | "live" | "done" | "killed" | "error";

export interface RunState {
  status: RunStatus;
  question: string;
  depth: number;
  energy: number;
  loopGuard: number;
  stability: number;
  confidence: number;
  budgetPct: number;
  tokensUsed: number;
  steps: TraceStep[];
  answer: string;
  stopReason: string;
  abort?: () => void;
  conversationId?: string;
  branchId?: string;
}

interface MonitorStore {
  run: RunState | null;
  start: (run: RunState) => void;
  patch: (p: Partial<RunState>) => void;
  addStep: (s: TraceStep) => void;
  clear: () => void;
}

export const useMonitor = create<MonitorStore>((set) => ({
  run: null,
  start: (run) => set({ run }),
  patch: (p) => set((st) => (st.run ? { run: { ...st.run, ...p } } : st)),
  addStep: (s) => set((st) => (st.run ? { run: { ...st.run, steps: [...st.run.steps, s] } } : st)),
  clear: () => set({ run: null }),
}));
