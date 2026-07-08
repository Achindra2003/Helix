import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listDeepRuns, getDeepRunRecord } from "@/lib/api";
import type { DeepRunRecord, DeepRunSummary, DeepRunTraceStep } from "@/lib/types";
import { Spinner } from "@/components/common/Feedback";
import { Step } from "./DeepReasoningMonitor";
import { formatDuration } from "@/lib/format";
import s from "./monitor.module.css";

const STATUS_GLYPH: Record<string, { glyph: string; color: string }> = {
  done: { glyph: "✓", color: "var(--verde)" },
  killed: { glyph: "◼", color: "var(--oxblood)" },
  error: { glyph: "✕", color: "var(--oxblood)" },
};

function stepText(p: DeepRunTraceStep): string {
  for (const k of ["thought", "synthesis", "surfaced_insight", "challenge"] as const) {
    const v = p[k];
    if (typeof v === "string" && v.trim()) return v;
  }
  return "";
}

/** The team's reasoning archive (P4): every persisted deep run of this
 *  conversation, newest first; click one for its full read-only trace —
 *  including the model + provenance stamp that says what produced it. */
export function RunHistory({ conversationId }: { conversationId: string }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["deep-runs", conversationId],
    queryFn: () => listDeepRuns(conversationId),
  });

  if (openId) return <RunRecordView runId={openId} onBack={() => setOpenId(null)} />;
  if (isLoading) return <div style={{ padding: 20 }}><Spinner /></div>;

  const items: DeepRunSummary[] = data?.items ?? [];
  if (items.length === 0) {
    return (
      <div className={s.idle}>
        <div className={s.idleTitle}>No runs recorded yet</div>
        <div className={s.idleText}>
          Every Deep Reasoning run leaves a durable record here — question, trace, outcome,
          and the model that produced it.
        </div>
      </div>
    );
  }

  return (
    <div className={s.trace}>
      {items.map((r) => {
        const st = STATUS_GLYPH[r.status] ?? { glyph: "·", color: "var(--ink-3)" };
        return (
          <button key={r.id} className={s.histRow} onClick={() => setOpenId(r.id)}>
            <span style={{ color: st.color, flex: "0 0 auto" }}>{st.glyph}</span>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span className={s.histQuestion}>{r.question || "(untitled run)"}</span>
              <span className={s.histMeta}>
                depth {r.depth} · stab {r.stability ? r.stability.toFixed(2) : "—"} ·{" "}
                {r.tokens_used} tok · {formatDuration(r.duration_ms)} ·{" "}
                {new Date(r.created_at).toLocaleString()}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function RunRecordView({ runId, onBack }: { runId: string; onBack: () => void }) {
  const { data: rec, isLoading } = useQuery({
    queryKey: ["deep-run-record", runId],
    queryFn: () => getDeepRunRecord(runId),
  });
  if (isLoading || !rec) return <div style={{ padding: 20 }}><Spinner /></div>;
  return <RecordBody rec={rec} onBack={onBack} />;
}

function RecordBody({ rec, onBack }: { rec: DeepRunRecord; onBack: () => void }) {
  const st = STATUS_GLYPH[rec.status] ?? { glyph: "·", color: "var(--ink-3)" };
  // Provenance entries, model first — render it; it's the trust story.
  const prov = Object.entries(rec.provenance ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== "");
  return (
    <div className={s.trace}>
      <button className={s.histBack} onClick={onBack}>← all runs</button>

      <div className={s.histQ}>{rec.question}</div>
      <div className={s.histMeta} style={{ marginBottom: 4 }}>
        <span style={{ color: st.color }}>{st.glyph} {rec.status}</span>
        {rec.stop_reason ? ` · ${rec.stop_reason}` : ""} · {new Date(rec.created_at).toLocaleString()}
      </div>
      <div className={s.readings} style={{ padding: "4px 0 10px" }}>
        <span className={s.reading}>depth <b>{rec.depth}</b></span>
        <span className={s.reading}>stability <b>{rec.stability ? rec.stability.toFixed(2) : "—"}</b></span>
        <span className={s.reading}>confidence <b>{rec.confidence ? rec.confidence.toFixed(2) : "—"}</b></span>
        <span className={s.reading}>tokens <b>{rec.tokens_used}</b></span>
        <span className={s.reading}>took <b>{formatDuration(rec.duration_ms)}</b></span>
      </div>

      {(rec.model || prov.length > 0) && (
        <div className={s.provBox}>
          <div className="eyebrow" style={{ marginBottom: 5 }}>Provenance</div>
          {rec.model && <div className={s.provRow}><span>model</span><b>{rec.model}</b></div>}
          {prov.map(([k, v]) => (
            <div key={k} className={s.provRow}><span>{k}</span><b>{String(v)}</b></div>
          ))}
        </div>
      )}

      {rec.trace?.steers?.length > 0 && (
        <div className={s.provBox} style={{ borderColor: "rgba(110,90,168,0.4)" }}>
          <div className="eyebrow" style={{ color: "var(--violet)", marginBottom: 5 }}>⟂ Steers</div>
          {rec.trace.steers.map((g, i) => (
            <div key={i} style={{ fontSize: 12.5, color: "var(--ink-2)", fontStyle: "italic" }}>“{g}”</div>
          ))}
        </div>
      )}

      {(rec.trace?.steps ?? []).map((p, i) => (
        <Step key={i} step={{
          kind: p.node,
          meta: `step ${p.idx} · depth ${p.depth}${typeof p.stability === "number" ? ` · stab ${p.stability.toFixed(2)}` : ""}`,
          text: stepText(p),
        }} />
      ))}

      {rec.answer && (
        <div className={s.answer}>
          <div className="eyebrow" style={{ color: "var(--oxblood)", marginBottom: 6 }}>Crystallized answer</div>
          <div style={{ fontSize: 14, lineHeight: 1.6, color: "var(--ink)" }}>{rec.answer}</div>
        </div>
      )}
    </div>
  );
}
