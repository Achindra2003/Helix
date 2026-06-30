import { useState } from "react";
import { Button } from "@/components/common/Button";
import s from "./chat.module.css";

export function Composer({
  provider, busy, onSend, onDeep, onLibrary,
}: {
  provider: string;
  busy: boolean;
  onSend: (text: string) => void;
  onDeep: (text: string) => void;
  onLibrary: () => void;
}) {
  const [text, setText] = useState("");

  function send() {
    const t = text.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
  }
  function deep() {
    const t = text.trim() || "What is the most defensible choice here, and why?";
    onDeep(t);
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
        <div style={{ flex: 1 }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-faint)" }}>☁ {provider}</span>
        <button className={s.sendBtn} onClick={send} disabled={busy} title="Send (Enter)">↑</button>
      </div>
    </div>
  );
}
