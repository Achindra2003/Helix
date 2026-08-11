import { useEffect, useRef, useState } from "react";
import s from "./chat.module.css";

export interface ThreadAction {
  key: string;
  label: string;
  glyph: string;
  danger?: boolean;
  onPick: () => void;
}

/**
 * The rare actions on a thread, behind one control.
 *
 * The stage header had accumulated eleven: rename, delete, replay, two
 * separate exports, link context, plus the two that matter. Every feature that
 * shipped claimed a place in it and nothing was ever ranked, which tells the
 * reader that nothing here is more important than anything else — and at
 * ~1280px it crushed the conversation title to "CH... STR...".
 *
 * Nothing is removed from the product; the rarely-used half moves one click
 * away so the always-used half can be seen. Conclude and Fork stay outside.
 */
export function ThreadMenu({ actions }: { actions: ThreadAction[] }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

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

  if (actions.length === 0) return null;

  return (
    <div className={s.menuWrap} ref={box}>
      <button
        className={s.menuBtn}
        aria-haspopup="menu"
        aria-expanded={open}
        title="More actions for this thread"
        onClick={() => setOpen((o) => !o)}
      >
        ⋯
      </button>
      {open && (
        <div className={s.menuList} role="menu">
          {actions.map((a) => (
            <button
              key={a.key}
              role="menuitem"
              className={`${s.menuItem} ${a.danger ? s.menuItemDanger : ""}`}
              onClick={() => { setOpen(false); a.onPick(); }}
            >
              <span className={s.menuGlyph} aria-hidden>{a.glyph}</span>
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
