// Deep Reasoning run state for the monitor panel.
import { create } from "zustand";

export interface TraceStep {
  kind: string; // langgraph node: reason/reflect/synthesize/breathe/surface/steer
  meta: string;
  text: string;
}

export type RunStatus = "idle" | "queued" | "live" | "waiting" | "done" | "killed" | "error";

export interface RunState {
  status: RunStatus;
  question: string;
  depth: number;
  energy: number;
  loopGuard: number;
  stability: number;
  confidence: number;
  // Convergence made visible: every per-cycle stability reading, plus the
  // run's resolved halting threshold (delivered on step payloads; 0.90 default).
  stabilityHistory: number[];
  threshold?: number;
  budgetPct: number;
  tokensUsed: number;
  steps: TraceStep[];
  answer: string;
  stopReason: string;
  abort?: () => void;
  conversationId?: string;
  branchId?: string;
  // Guided runs (FR-11): the server-side run handle, and the callback the
  // monitor invokes to resume a paused run with (optional) human guidance.
  runId?: string;
  onSteer?: (guidance: string) => void;
  // Waiting behind the workspace's concurrency cap (the `queued` frame).
  queuePosition?: number;
  // False on watch-only runs (a teammate's) — hides the Stop control.
  canControl?: boolean;
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
