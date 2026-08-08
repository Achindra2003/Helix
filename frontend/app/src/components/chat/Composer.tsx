import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Button } from "@/components/common/Button";
import { DeepButton } from "./DeepButton";
import { MentionPicker, mentionAt } from "./MentionPicker";
import { ACTION, PLACE } from "@/lib/glyphs";
import s from "./chat.module.css";

export function Composer({
  provider, busy, onSend, onDeep, onAgent, onNote, agentHint, onLibrary, onDraftChange, draft, onDraftConsumed, wid,
}: {
  provider: string;
  /** The workspace whose members `@` resolves against. */
  wid?: string;
  busy: boolean;
  onSend: (text: string) => void;
  onDeep: (text: string, guided: boolean, mode?: string) => void;
  // Agent mode (FR-14): the model gets hands — the workspace's allowed tools,
  // with sensitive calls pausing for approval.
  onAgent: (text: string) => void;
  // Say it to the room instead of to Helix. Same box, different addressee —
  // a separate comment field would put team talk somewhere nobody looks.
  onNote: (text: string) => void;
  // What this workspace's agent can currently do (tooltip: tool names, or why
  // agent runs are unavailable).
  agentHint?: string;
  onLibrary: () => void;
  // Proactive resurfacing: the parent watches what's being typed and can
  // surface "a teammate already explored this" before the send happens.
  onDraftChange?: (text: string) => void;
  // "Edit last message" hand-off: the deleted message's text lands here for
  // the author to revise and resend (edit = delete + resend, by design).
  draft?: string | null;
  onDraftConsumed?: () => void;
}) {
  const [text, setText] = useState("");
  const reduce = useReducedMotion();
  // Guided mode (FR-11): the deep run pauses between refinement cycles so you
  // can steer it mid-flight from the monitor. Off = classic self-halting run.
  const [guided, setGuided] = useState(false);

  // Every text change flows through here so the parent's resurfacing watcher
  // sees sends/clears too, not just keystrokes.
  function update(t: string) {
    setText(t);
    onDraftChange?.(t);
  }

  useEffect(() => {
    if (draft) {
      update(draft);
      onDraftConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  function send() {
    const t = text.trim();
    if (!t || busy) return;
    onSend(t);
    update("");
  }
  function deep(mode: string) {
    const t = text.trim() || "What is the most defensible choice here, and why?";
    onDeep(t, guided, mode);
    update("");
  }
  function agent() {
    const t = text.trim();
    if (!t || busy) return;
    onAgent(t);
    update("");
  }
  function note() {
    const t = text.trim();
    if (!t) return;
    onNote(t);
    update("");
  }

  // `@` addresses a teammate. The picker is mounted only while the caret sits
  // in an unfinished handle, and it takes Enter before the composer does —
  // otherwise picking a name would send the message.
  const taRef = useRef<HTMLTextAreaElement>(null);
  const [caret, setCaret] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const mention = dismissed ? null : mentionAt(text, caret);

  function pickMention(handle: string) {
    const m = mentionAt(text, caret);
    if (!m) return;
    const next = text.slice(0, m.from) + "@" + handle + " " + text.slice(caret);
    update(next);
    const at = m.from + handle.length + 2;
    requestAnimationFrame(() => {
      taRef.current?.focus();
      taRef.current?.setSelectionRange(at, at);
      setCaret(at);
    });
  }

  return (
    <div className={s.composer}>
      {wid && mention && (
        <MentionPicker wid={wid} query={mention.query}
          onPick={pickMention} onDismiss={() => setDismissed(true)} />
      )}
      <textarea
        ref={taRef}
        className={s.ta}
        rows={2}
        placeholder="Continue the thread, or escalate to Deep Reasoning… @ a teammate to ask them"
        value={text}
        onChange={(e) => { update(e.target.value); setCaret(e.target.selectionStart ?? 0); setDismissed(false); }}
        onSelect={(e) => setCaret((e.target as HTMLTextAreaElement).selectionStart ?? 0)}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
      />
      <div className={s.composerRow}>
        <div className={s.composerActions}>
        <Button onClick={onLibrary} style={{ padding: "6px 11px", fontSize: 12 }} title="Insert from prompt library">
          <span style={{ color: "var(--oxblood)" }} aria-hidden>{PLACE.prompts}</span> Library
        </Button>
        <DeepButton busy={busy} guided={guided} onGuidedChange={setGuided} onRun={deep} />
        <Button onClick={agent} disabled={busy} style={{ padding: "6px 11px", fontSize: 12 }}
          title={agentHint ?? "Agent: Helix answers with tools — searching before it speaks"}>
          <span style={{ color: "var(--oxblood)" }} aria-hidden>{ACTION.agent}</span> Agent
        </Button>
        <Button onClick={note} disabled={!text.trim()} style={{ padding: "6px 11px", fontSize: 12 }}
          title="Say this to your teammates instead of to Helix — it stays in the thread, and the model never reads it">
          <span style={{ color: "var(--verde)" }} aria-hidden>{ACTION.note}</span> Team
        </Button>
        </div>
        <div className={s.composerSend}>
          {/* Always rendered, faded when there's nothing to send: conditionally
              mounting it is what used to push this button onto a second row. */}
          <span className={`mono ${s.composerHint} ${text.trim() ? s.composerHintOn : ""}`}
            aria-hidden={!text.trim()}
            style={{ fontSize: 10, color: "var(--ink-3)", letterSpacing: "0.04em" }}>
            ↵ ask Helix · ⇧↵ new line
          </span>
          <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{provider}</span>
          <motion.button className={s.sendBtn} onClick={send} disabled={busy} title="Send (Enter)"
            whileHover={reduce || busy ? undefined : { scale: 1.08, y: -1 }}
            whileTap={{ scale: 0.9 }}
            transition={{ type: "spring", stiffness: 500, damping: 20 }}>↑</motion.button>
        </div>
      </div>
    </div>
  );
}
