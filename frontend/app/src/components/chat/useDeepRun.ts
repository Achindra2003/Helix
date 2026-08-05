// The Deep Reasoning run as its own controller — the sibling of useAgentRun.
//
// Like an agent turn, a deep run arrives in SEGMENTS: a guided run pauses for
// human guidance, which ends one stream, and each steer opens the next. Unlike
// an agent turn it also outlives the tab — the run is server-side, so a reload
// has to find it again and reattach, replaying its event log from 0 to rebuild
// the monitor before following live.
//
// That is roughly 150 lines of lifecycle that had no business sitting inside a
// view which also owns conversations, branches, history, drawers and replay.
// The split follows the same rule useAgentRun set: the view keeps ownership of
// what is on screen, so refreshing the transcript arrives here as a callback
// rather than this hook learning how to build a message list.
import { useEffect } from "react";
import { streamSSE, attachSSE } from "@/lib/sse";
import { getDeepRunStatus, killDeepRun } from "@/lib/api";
import { useMonitor } from "@/store/monitor";
import { useNotifications } from "@/store/notifications";
import { can } from "@/lib/rbac";
import type { Role, RunEvent } from "@/lib/types";

// Deep runs execute server-side and outlive the tab: remember the in-flight
// run so a reload can reattach to its stream instead of showing a dead monitor.
const deepKey = (wid: string) => `helix:deeprun:${wid}`;

interface SavedDeepRun {
  runId: string; conversationId: string; branchId: string; question: string; guided: boolean;
}

/** The most legible line in a step payload — engine nodes name their output
 *  differently depending on which one produced it. Exported because the live
 *  fan-out renders a teammate's run through the same monitor. */
export function pickText(p: Record<string, unknown>): string {
  if (!p) return "";
  for (const k of ["thought", "synthesis", "surfaced_insight", "insight", "reflection", "seed"]) {
    const v = p[k];
    if (typeof v === "string" && v.trim()) return v;
  }
  const v = Object.values(p).find((x) => typeof x === "string" && (x as string).length > 4);
  return (v as string) ?? "";
}

export function useDeepRun({
  wid, role, activeConvId, ensureConversation, refreshHistory, isViewing,
}: {
  wid: string | undefined;
  role: Role;
  activeConvId: string | null;
  /** Create a conversation if there isn't one, and answer with its branch. */
  ensureConversation: () => Promise<string | null>;
  /** Reload the transcript for a branch once a run has truly finished. */
  refreshHistory: (branchId: string) => void;
  /** Is the user still looking at this branch? A run that finishes after they
   *  navigated away must not overwrite whatever they are reading now. */
  isViewing: (branchId: string) => boolean;
}) {
  const monitor = useMonitor();

  function handleDeepEvent(ev: RunEvent) {
    const run = useMonitor.getState().run;
    if (!run) return;
    if (ev.kind === "deep_run") {
      monitor.patch({ runId: ev.run_id });
      if (wid) {
        const saved: SavedDeepRun = {
          runId: ev.run_id, conversationId: run.conversationId ?? "", branchId: run.branchId ?? "",
          question: run.question, guided: !!run.onSteer,
        };
        sessionStorage.setItem(deepKey(wid), JSON.stringify(saved));
      }
    } else if (ev.kind === "queued") {
      // Waiting behind the workspace's concurrency cap — say so instead of stalling.
      monitor.patch({ status: "queued", queuePosition: ev.position });
    } else if (ev.kind === "step") {
      const p = ev.payload ?? {};
      const num = (k: string, d: number) => (typeof p[k] === "number" ? (p[k] as number) : d);
      // Convergence viz: collect each cycle's stability reading (and the run's
      // resolved halting threshold) for the sparkline + closing ring.
      const stabNow = typeof p.stability === "number" ? (p.stability as number) : null;
      const thr = typeof p.stability_threshold === "number" ? (p.stability_threshold as number) : undefined;
      monitor.patch({
        depth: ev.depth ?? run.depth,
        energy: ev.energy ?? run.energy,
        loopGuard: num("loop_guard", run.loopGuard),
        stability: num("stability", run.stability),
        confidence: num("confidence", run.confidence),
        ...(stabNow !== null && stabNow !== run.stabilityHistory[run.stabilityHistory.length - 1]
          ? { stabilityHistory: [...run.stabilityHistory, stabNow] } : {}),
        ...(thr !== undefined ? { threshold: thr } : {}),
        // A queued run has started; a replayed pause has been steered past.
        ...(run.status === "queued" || run.status === "waiting" ? { status: "live" as const } : {}),
      });
      const stab = typeof p.stability === "number" ? ` · stab ${(p.stability as number).toFixed(2)}` : "";
      monitor.addStep({ kind: ev.node, meta: `step ${ev.idx} · depth ${ev.depth}${stab}`, text: pickText(p) });
    } else if (ev.kind === "budget") {
      monitor.patch({ budgetPct: Math.round(ev.pct <= 1 ? ev.pct * 100 : ev.pct), tokensUsed: ev.tokens_used ?? run.tokensUsed });
    } else if (ev.kind === "token") {
      monitor.patch({ answer: ((useMonitor.getState().run?.answer ?? "") + ev.text).replace(/^\s*\[answer\]\s*/i, "") });
    } else if (ev.kind === "waiting") {
      monitor.addStep({ kind: "steer", meta: "paused for guidance", text: "The loop is holding — steer it, or let it continue." });
      monitor.patch({ status: "waiting" });
    } else if (ev.kind === "complete") {
      monitor.patch({ status: ev.status === "killed" ? "killed" : ev.status === "error" ? "error" : "done", stopReason: ev.stop_reason });
      if (wid) sessionStorage.removeItem(deepKey(wid));
      // Your own run finished while you weren't looking (backgrounded tab):
      // a bell notice, plus a browser notification if permission was granted.
      if (document.hidden) {
        useNotifications.getState().add({
          text: `Your deep run ${ev.status === "done" ? "finished" : ev.status} (${ev.stop_reason})`,
          conversationId: run.conversationId,
        });
        if (typeof Notification !== "undefined" && Notification.permission === "granted") {
          try {
            new Notification("Helix — deep run finished", { body: run.question.slice(0, 120) });
          } catch { /* notification is an enhancement, never an error */ }
        }
      }
    } else if (ev.kind === "assistant_node") {
      const cur = useMonitor.getState().run;
      if (cur && !cur.answer && ev.node.content) monitor.patch({ answer: ev.node.content });
    }
  }

  /** Await one SSE segment of a deep run; a guided run has several (each pause
   *  ends the stream, each steer opens the next). History refreshes only when
   *  the run truly finishes — a paused run has no assistant reply yet. */
  async function finishDeepSegment(done: Promise<void>, branchId: string) {
    try {
      await done;
      const cur = useMonitor.getState().run;
      if (cur && cur.status === "live") monitor.patch({ status: "done", stopReason: cur.stopReason || "ended" });
    } catch (e: any) {
      const cur = useMonitor.getState().run;
      if (cur) monitor.patch({ status: e?.name === "AbortError" ? "killed" : "error", stopReason: e?.name === "AbortError" ? "killed by operator" : (e?.message ?? "error") });
    }
    const status = useMonitor.getState().run?.status;
    if (status !== "waiting" && status !== "live" && status !== "queued" && wid) {
      // Terminal on this client — a reload should not reattach to it.
      sessionStorage.removeItem(deepKey(wid));
    }
    if (status !== "waiting" && isViewing(branchId)) refreshHistory(branchId);
  }

  async function steerRun(guidance: string) {
    const cur = useMonitor.getState().run;
    if (!cur?.runId || !cur.branchId || cur.status !== "waiting") return;
    monitor.patch({ status: "live" });
    monitor.addStep({ kind: "steer", meta: "human guidance", text: guidance || "(continue unchanged)" });
    const h = streamSSE(`/conversations/deep/runs/${cur.runId}/steer`, { guidance }, handleDeepEvent);
    monitor.patch({ abort: h.abort });
    await finishDeepSegment(h.done, cur.branchId);
  }

  async function onDeep(text: string, guided: boolean) {
    const branchId = await ensureConversation();
    if (!branchId || !activeConvId) return;
    // Deep runs take minutes and survive the tab — ask (once, lazily) to be
    // allowed to notify when one finishes in the background. Denial is fine.
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }
    const h = streamSSE(`/conversations/${branchId}/deep`, { prompt: text, steerable: guided }, handleDeepEvent);
    monitor.start({
      status: "live", question: text, depth: 0, energy: 0, loopGuard: 0, stability: 0, confidence: 0,
      stabilityHistory: [],
      budgetPct: 0, tokensUsed: 0, steps: [], answer: "", stopReason: "",
      abort: h.abort, conversationId: activeConvId, branchId,
      canControl: can(role, "run.control"),
      onSteer: guided ? (g) => { steerRun(g); } : undefined,
    });
    await finishDeepSegment(h.done, branchId);
  }

  async function stopRun() {
    const cur = useMonitor.getState().run;
    if (!cur) return;
    if (cur.runId) {
      try { await killDeepRun(cur.runId); return; } catch { /* fall back to abort */ }
    }
    cur.abort?.();
  }

  // Reconnect-on-load (AI-LANE-CONTRACTS §2.2): if this workspace has an
  // in-flight deep run from a previous page load, reattach to its stream —
  // replaying the event log from 0 rebuilds the whole monitor (gauges, trace,
  // sparkline), then follows live. A finished/expired run just clears itself.
  useEffect(() => {
    if (!wid) return;
    const raw = sessionStorage.getItem(deepKey(wid));
    if (!raw) return;
    let saved: SavedDeepRun;
    try { saved = JSON.parse(raw); } catch { sessionStorage.removeItem(deepKey(wid)); return; }
    if (!saved?.runId) { sessionStorage.removeItem(deepKey(wid)); return; }
    (async () => {
      try {
        const st = await getDeepRunStatus(saved.runId);
        if (st.status === "done" || st.status === "error" || st.status === "killed") {
          sessionStorage.removeItem(deepKey(wid));
          return;
        }
        monitor.start({
          status: st.status === "queued" ? "queued" : "live",
          question: saved.question, depth: 0, energy: 0, loopGuard: 0, stability: 0, confidence: 0,
          stabilityHistory: [], budgetPct: 0, tokensUsed: 0, steps: [], answer: "", stopReason: "",
          conversationId: saved.conversationId, branchId: saved.branchId, runId: saved.runId,
          queuePosition: st.queue_position ?? undefined,
          canControl: can(role, "run.control"),
          onSteer: saved.guided ? (g) => { steerRun(g); } : undefined,
        });
        const h = attachSSE(`/conversations/deep/runs/${saved.runId}/stream?after=0`, handleDeepEvent);
        monitor.patch({ abort: h.abort });
        await finishDeepSegment(h.done, saved.branchId);
      } catch {
        // 404: the run finished and its live handle expired — the assistant
        // node is already in history, nothing to reattach to.
        sessionStorage.removeItem(deepKey(wid));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wid]);

  // Only the two the view actually drives. Steering is reached through the
  // monitor's own onSteer, and the event handler is this hook's business.
  return { onDeep, stopRun };
}
