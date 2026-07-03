import { useEffect, useRef, useState } from "react";
import { useMonitor, type TraceStep } from "@/store/monitor";
import { Button } from "@/components/common/Button";
import s from "./monitor.module.css";

const KIND_COLOR: Record<string, string> = {
  reason: "var(--ink-2)", think: "var(--ink-2)",
  reflect: "var(--violet)", synthesize: "var(--oxblood)", synth: "var(--oxblood)",
  breathe: "var(--ink-3)", surface: "var(--gilt)", steer: "var(--violet)",
};

const RING_C = 2 * Math.PI * 40; // circumference of the r=40 arc

/** The ring *closes* as the answer converges: the gap is driven by stability
 *  against the run's halting threshold, and the head meets the tail on
 *  convergence. A killed/errored run freezes mid-gap — honestly incomplete. */
function OuroborosRing({ depth, spin, progress, closed }: {
  depth: number; spin: boolean; progress: number; closed: boolean;
}) {
  const gap = closed ? 0 : 8 + (1 - Math.min(Math.max(progress, 0), 1)) * 56;
  return (
    <div className={s.ring}>
      <svg viewBox="0 0 100 100" width={78} height={78} className={spin ? s.ringSpin : ""} aria-hidden>
        <circle
          className={s.ringArc}
          cx="50" cy="50" r="40" fill="none"
          stroke={closed ? "var(--gilt-1)" : "var(--oxblood)"} strokeWidth="2.5"
          strokeDasharray={`${RING_C - gap} ${gap}`} strokeLinecap="round"
        />
        <circle cx="10" cy="50" r="4" fill="var(--gilt-2)" />
      </svg>
      <div className={s.ringCenter}>
        <span className={s.depth}>{depth}</span>
        <span className={s.depthLabel}>depth</span>
      </div>
    </div>
  );
}

/** Axes-free sparkline of per-cycle stability climbing toward the dashed
 *  halting threshold; locks gilt with a "converged" stamp when it crosses.
 *  Numbers live in the readings row — this shows the *settling*. */
function StabilitySparkline({ history, threshold, converged }: {
  history: number[]; threshold: number; converged: boolean;
}) {
  if (history.length < 2) return null;
  const W = 300, H = 44, padX = 6, padT = 7, padB = 7;
  const x = (i: number) => padX + (i * (W - 2 * padX)) / Math.max(history.length - 1, 7);
  const y = (v: number) => padT + (1 - Math.min(Math.max(v, 0), 1)) * (H - padT - padB);
  const d = history.map((v, i) => `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const crossed = converged || history[history.length - 1] >= threshold;
  const line = crossed ? "var(--gilt-1)" : "var(--ink-2)";
  return (
    <div className={s.spark}>
      <div className={s.sparkTop}>
        <span>CONVERGENCE</span>
        {crossed && <span className={s.sparkStamp}>❧ converged</span>}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img"
        aria-label={`Answer stability across ${history.length} cycles; halting threshold ${threshold.toFixed(2)}`}>
        <line x1={padX} x2={W - padX} y1={y(threshold)} y2={y(threshold)}
          stroke="var(--ink-faint)" strokeWidth="1" strokeDasharray="4 4" />
        <text x={W - padX} y={y(threshold) - 3} textAnchor="end" className={s.sparkThr}>
          halts at {threshold.toFixed(2)}
        </text>
        <path d={d} fill="none" stroke={line} strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={x(history.length - 1)} cy={y(history[history.length - 1])} r="3"
          fill={line} stroke="var(--paper)" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

// The recursive engine's reasoning topology (FR-10): the canonical node cycle.
const TOPO = [
  { keys: ["reason", "think"], label: "reason" },
  { keys: ["reflect"], label: "reflect" },
  { keys: ["synthesize", "synth"], label: "synthesize" },
  { keys: ["breathe"], label: "breathe" },
  { keys: ["surface"], label: "surface" },
];

function Topology({ steps }: { steps: TraceStep[] }) {
  const seen = new Set(steps.map((s) => s.kind));
  const current = steps.length ? steps[steps.length - 1].kind : "";
  return (
    <div className={s.topology} title="Reasoning topology — nodes light up as the engine runs">
      {TOPO.map((n, i) => {
        const isCur = n.keys.includes(current);
        const isSeen = n.keys.some((k) => seen.has(k));
        return (
          <span key={n.label} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <span className={`${s.topoNode} ${isCur ? s.topoCur : isSeen ? s.topoSeen : ""}`}>{n.label}</span>
            {i < TOPO.length - 1 && <span className={s.topoArrow}>→</span>}
          </span>
        );
      })}
    </div>
  );
}

function Step({ step }: { step: TraceStep }) {
  const c = KIND_COLOR[step.kind] ?? "var(--ink-3)";
  return (
    <div className={s.step}>
      <div className={s.stepRail}>
        <span className={s.stepDot} style={{ background: c }} />
        <span className={s.stepLine} />
      </div>
      <div className={s.stepBody}>
        <div>
          <span className={s.stepKind} style={{ color: c }}>{step.kind}</span>
          <span className={s.stepMeta}>{step.meta}</span>
        </div>
        {step.text && <div className={s.stepText}>{step.text}</div>}
      </div>
    </div>
  );
}

export function DeepReasoningMonitor() {
  const { run, clear } = useMonitor();
  const traceRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (traceRef.current) traceRef.current.scrollTop = traceRef.current.scrollHeight;
  }, [run?.steps.length, run?.answer]);

  const threshold = run?.threshold ?? 0.9;
  const holding = run?.status === "waiting";

  return (
    <div className={`${s.pane} ${holding ? s.holding : ""} monitor-pane`}>
      <div className={s.head}>
        <span style={{ color: "var(--oxblood)", fontSize: 15 }}>⟳</span>
        <span className="eyebrow" style={{ flex: 1, letterSpacing: "0.14em" }}>Deep Reasoning</span>
        <span className={`${s.status} ${run?.status === "live" ? s.statusLive : run?.status === "done" ? s.statusDone : holding ? s.statusHold : ""}`}>
          {run ? statusLabel(run.status) : "idle"}
        </span>
      </div>

      {!run ? (
        <div className={s.idle}>
          <svg viewBox="0 0 120 120" width={92} height={92} style={{ opacity: 0.5 }} aria-hidden>
            <circle cx="60" cy="60" r="46" fill="none" stroke="var(--rule)" strokeWidth="1" />
            <circle cx="60" cy="60" r="33" fill="none" stroke="var(--rule-soft)" strokeWidth="1" strokeDasharray="2 5" />
            <circle cx="60" cy="60" r="20" fill="none" stroke="var(--rule-soft)" strokeWidth="1" />
            <circle cx="14" cy="60" r="3" fill="var(--gilt)" />
          </svg>
          <div className={s.idleTitle}>The monitor is quiet</div>
          <div className={s.idleText}>
            Escalate a hard question into a recursive reason → reflect → synthesize run. Every step
            appears here — with a kill switch and a live budget meter.
          </div>
        </div>
      ) : (
        <>
          <div className={s.gauges}>
            <OuroborosRing
              depth={run.depth}
              spin={run.status === "live"}
              progress={threshold ? run.stability / threshold : 0}
              closed={run.status === "done"}
            />
            <div className={s.meters}>
              <div>
                <div className={s.meterTop}><span>ENERGY</span><span>{Math.round(run.energy)}</span></div>
                <div className={s.bar}><div className={s.fill} style={{ width: `${Math.min(100, run.energy)}%`, background: "var(--verde)" }} /></div>
              </div>
              <div>
                <div className={s.meterTop}><span>BUDGET</span><span style={{ color: run.budgetPct > 80 ? "var(--ember)" : undefined }}>{run.budgetPct}%</span></div>
                <div className={s.bar}><div className={s.fill} style={{ width: `${run.budgetPct}%`, background: run.budgetPct > 80 ? "var(--ember)" : "var(--oxblood)" }} /></div>
              </div>
            </div>
          </div>

          <Topology steps={run.steps} />
          <div className={s.readings}>
            <span className={s.reading}>loop-guard <b>{run.loopGuard}</b></span>
            <span className={s.reading}>stability <b>{run.stability ? run.stability.toFixed(2) : "—"}</b></span>
            <span className={s.reading}>confidence <b>{run.confidence ? run.confidence.toFixed(2) : "—"}</b></span>
            <span className={s.reading}>tokens <b>{run.tokensUsed || 0}</b></span>
          </div>

          <StabilitySparkline
            history={run.stabilityHistory}
            threshold={threshold}
            converged={run.status === "done"}
          />

          <div className={s.trace} ref={traceRef}>
            {run.steps.map((step, i) => <Step key={i} step={step} />)}
            {run.answer && (
              <div className={s.answer}>
                <div className="eyebrow" style={{ color: "var(--oxblood)", marginBottom: 6 }}>Crystallized answer</div>
                <div style={{ fontSize: 14, lineHeight: 1.6, color: "var(--ink)" }}>{run.answer}</div>
              </div>
            )}
            {run.status !== "live" && run.stopReason && (
              <div className={s.finish} style={{ color: run.status === "done" ? "var(--verde)" : "var(--oxblood)" }}>
                {run.status === "done" ? "✓" : "◼"} {run.status} · {run.stopReason}
              </div>
            )}
          </div>

          {run.status === "waiting" && run.onSteer && <SteerBox onSteer={run.onSteer} />}

          <div className={s.controls}>
            {run.status === "live" ? (
              <>
                {run.onSteer && (
                  <button className={s.steer} title="Guided run — it will pause for you at the next reasoning checkpoint" disabled>
                    ⟂ pausing at next checkpoint…
                  </button>
                )}
                <button className={s.kill} onClick={() => run.abort?.()}>◼ Kill switch</button>
              </>
            ) : run.status === "waiting" ? (
              <button className={s.kill} onClick={() => run.abort?.()}>◼ Kill switch</button>
            ) : (
              <Button className={s.dismiss} onClick={clear}>Dismiss</Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/** Shown while a guided run is paused at a steer checkpoint (FR-11): inject
 *  guidance to redirect the next reasoning cycle, or let it continue as-is. */
function SteerBox({ onSteer }: { onSteer: (guidance: string) => void }) {
  const [guidance, setGuidance] = useState("");
  function go(g: string) {
    onSteer(g);
    setGuidance("");
  }
  return (
    <div className={s.steerBox}>
      <div className="eyebrow" style={{ color: "var(--violet)", marginBottom: 6 }}>⟂ Steer the reasoning</div>
      <textarea
        className={s.steerInput}
        rows={2}
        placeholder="Redirect the next cycle… e.g. “weigh cost above all else”"
        value={guidance}
        onChange={(e) => setGuidance(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(guidance.trim()); } }}
        autoFocus
      />
      <div style={{ display: "flex", gap: 7, marginTop: 7 }}>
        <Button onClick={() => go(guidance.trim())} style={{ fontSize: 12, padding: "5px 11px", borderColor: "var(--violet)", color: "var(--violet)" }}>
          ⟂ Steer
        </Button>
        <Button onClick={() => go("")} style={{ fontSize: 12, padding: "5px 11px" }} title="Resume without guidance">
          Continue as-is
        </Button>
      </div>
    </div>
  );
}

function statusLabel(s: string) {
  return ({ live: "● running", waiting: "⟂ holding for you", done: "converged", killed: "killed", error: "error" } as Record<string, string>)[s] ?? s;
}
