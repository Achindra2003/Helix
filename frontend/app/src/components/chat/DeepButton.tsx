import { useEffect, useRef, useState } from "react";
import { getReasoningModes } from "@/lib/api";
import type { ReasoningMode } from "@/lib/types";
import { ACTION } from "@/lib/glyphs";
import s from "./chat.module.css";

/** Last mode used, per browser. A team settles into one for a stretch of work,
 *  and re-picking it every time would make the choice feel like a tax. */
const MODE_PREF = "helix.deepMode";

/**
 * Escalate to Deep Reasoning, and say what kind of thinking to do.
 *
 * Five presets ship in the engine — Explore, Analyze, Create, Solve,
 * Philosophize — each with its own depth, energy curve, steer interval and four
 * distinct prompts. Until now the API pinned one server-wide `.env` string, so
 * every workspace on an instance got Analyze and the other four were
 * unreachable. That is most of why the product read as generic: a literature
 * survey and a debugging session ran the identical loop.
 *
 * Mode belongs *here*, at the moment of escalation, rather than in workspace
 * settings — "wander and discover" versus "decompose and test" is a property of
 * the question, and it changes within one team within one afternoon.
 *
 * A split button, so this costs the crowded composer row nothing: the face runs
 * with the mode you last used, the caret opens the choice. `guided` moved in
 * here too — it is the same decision (how should this run behave), and it was
 * previously a bare `⟂ guided` checkbox that explained itself to nobody.
 */
export function DeepButton({ busy, guided, onGuidedChange, onRun }: {
  busy: boolean;
  guided: boolean;
  onGuidedChange: (v: boolean) => void;
  onRun: (mode: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [modes, setModes] = useState<ReasoningMode[]>([]);
  const [mode, setMode] = useState<string>(() => {
    try { return localStorage.getItem(MODE_PREF) ?? ""; } catch { return ""; }
  });
  const box = useRef<HTMLDivElement>(null);

  // Fetched once the menu is first opened, not on mount: every chat screen
  // would otherwise pay for a list most sessions never look at.
  useEffect(() => {
    if (!open || modes.length) return;
    getReasoningModes()
      .then((r) => {
        setModes(r.modes);
        // Only now do we know what the instance default is; adopt it so the
        // menu can show which one the face button would run.
        setMode((m) => m || r.default);
      })
      .catch(() => { /* the face button still runs, on the server default */ });
  }, [open, modes.length]);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  function run(next: string) {
    setMode(next);
    try { localStorage.setItem(MODE_PREF, next); } catch { /* private mode */ }
    setOpen(false);
    onRun(next);
  }

  const current = modes.find((m) => m.id === mode);

  return (
    <div className={s.deepWrap} ref={box}>
      <button
        className={s.deepFace}
        disabled={busy}
        onClick={() => onRun(mode || "")}
        title={current
          ? `Escalate to Deep Reasoning — ${current.label}: ${current.description}`
          : "Escalate to Deep Reasoning: a recursive reason → reflect → synthesize run"}
      >
        <span aria-hidden>{ACTION.deep}</span> Deep Reasoning
        {current && <span className={s.deepMode}>{current.label}</span>}
      </button>
      <button
        className={s.deepCaret}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Choose how to reason"
        title="Choose how to reason"
        onClick={() => setOpen((o) => !o)}
      >
        <span aria-hidden>⌄</span>
      </button>

      {open && (
        <div className={s.deepMenu} role="menu">
          <div className={s.deepMenuHead}>How should it think?</div>
          {modes.map((m) => (
            <button
              key={m.id}
              role="menuitemradio"
              aria-checked={m.id === mode}
              className={`${s.deepItem} ${m.id === mode ? s.deepItemOn : ""}`}
              onClick={() => run(m.id)}
            >
              <span className={s.deepItemLabel}>{m.label}</span>
              <span className={s.deepItemDesc}>{m.description}</span>
            </button>
          ))}
          {!modes.length && <div className={s.deepItemDesc} style={{ padding: "8px 12px" }}>Loading…</div>}

          {/* Guided lived in the composer row as a bare "⟂ guided" checkbox.
              It is the same decision as the mode — how this run should behave —
              and here it can afford the sentence that explains it. */}
          <label className={s.deepGuided}>
            <input
              type="checkbox"
              checked={guided}
              onChange={(e) => onGuidedChange(e.target.checked)}
              style={{ accentColor: "var(--violet)" }}
            />
            <span>
              <span className={s.deepItemLabel}>Guided</span>
              <span className={s.deepItemDesc}>
                Pause between cycles so you can redirect the reasoning from the monitor.
              </span>
            </span>
          </label>
        </div>
      )}
    </div>
  );
}
