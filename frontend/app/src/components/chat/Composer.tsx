import { useState } from "react";
import { Button } from "@/components/common/Button";
import s from "./chat.module.css";

export function Composer({
  provider, busy, onSend, onDeep, onLibrary,
}: {
  provider: string;
  busy: boolean;
  onSend: (text: string) => void;
  onDeep: (text: string, guided: boolean) => void;
  onLibrary: () => void;
}) {
  const [text, setText] = useState("");
  // Guided mode (FR-11): the deep run pauses between refinement cycles so you
  // can steer it mid-flight from the monitor. Off = classic self-halting run.
  const [guided, setGuided] = useState(false);

  function send() {
    const t = text.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
  }
  function deep() {
    const t = text.trim() || "What is the most defensible choice here, and why?";
    onDeep(t, guided);
    setText("");
  }

  return (
    <div className={s.composer}>
      <textarea
        className={s.ta}
        rows={2}
        placeholder="Continue the thread, or escalate to Deep Reasoning…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
      />
      <div className={s.composerRow}>
        <Button onClick={onLibrary} style={{ padding: "6px 11px", fontSize: 12.5 }} title="Insert from prompt library">
          <span style={{ color: "var(--oxblood)" }}>▦</span> Library
        </Button>
        <Button onClick={deep} disabled={busy} style={{ padding: "6px 11px", fontSize: 12.5, borderColor: "var(--oxblood)", color: "var(--oxblood)" }} title="Escalate to Deep Reasoning">
          <span>⟳</span> Deep Reasoning
        </Button>
        <label
          title="Guided: the run pauses between reasoning cycles so you can steer it from the monitor"
          style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5, color: guided ? "var(--violet)" : "var(--ink-3)", cursor: "pointer", userSelect: "none" }}
        >
          <input type="checkbox" checked={guided} onChange={(e) => setGuided(e.target.checked)} style={{ accentColor: "var(--violet)" }} />
          ⟂ guided
        </label>
        <div style={{ flex: 1 }} />
        {text.trim() && (
          <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)", letterSpacing: "0.04em" }}>
            ↵ send · ⇧↵ new line
          </span>
        )}
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>☁ {provider}</span>
        <button className={s.sendBtn} onClick={send} disabled={busy} title="Send (Enter)">↑</button>
      </div>
    </div>
  );
}
