import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listMembers } from "@/lib/api";
import { initialOf, colorFor } from "@/lib/format";
import s from "./chat.module.css";

/**
 * `@` in the composer, resolved against the people actually in the workspace.
 *
 * A mention only means anything if you can write it without guessing. The
 * handle is the local part of a teammate's email — nobody registers it, so it
 * cannot drift from the person — but nobody memorises their colleagues'
 * addresses either, which is what this list is for.
 *
 * It appears only while the caret sits in an unfinished `@word`. That is the
 * whole trigger condition: no button, no mode, nothing on screen until you
 * have started typing a name.
 */

/** The `@word` the caret is inside, or null. Only a run with no whitespace and
 *  only at a word boundary — "priya@lab.edu" is an address, not a mention. */
export function mentionAt(text: string, caret: number): { query: string; from: number } | null {
  let i = caret - 1;
  while (i >= 0 && /[A-Za-z0-9._%+-]/.test(text[i])) i--;
  if (i < 0 || text[i] !== "@") return null;
  if (i > 0 && !/\s/.test(text[i - 1])) return null;
  return { query: text.slice(i + 1, caret).toLowerCase(), from: i };
}

export function MentionPicker({
  wid, query, onPick, onDismiss,
}: {
  wid: string;
  query: string;
  onPick: (handle: string) => void;
  onDismiss: () => void;
}) {
  const { data } = useQuery({
    queryKey: ["members", wid],
    queryFn: () => listMembers(wid),
    enabled: !!wid,
    staleTime: 60_000,
  });
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const matches = useMemo(() => {
    const all = (data ?? []).map((m) => ({ ...m, handle: m.email.split("@")[0] }));
    return all.filter((m) => m.handle.toLowerCase().startsWith(query)).slice(0, 6);
  }, [data, query]);

  useEffect(() => { setActive(0); }, [query]);

  // Keydown on the document in the capture phase, and every handled key is
  // stopped dead — not merely default-prevented. React 18 listens on the root
  // container, so preventDefault alone let Enter both pick the name *and* reach
  // the composer, which sent the half-written message.
  useEffect(() => {
    if (matches.length === 0) return;
    const onKey = (e: KeyboardEvent) => {
      const take = () => { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); };
      if (e.key === "ArrowDown") { take(); setActive((i) => (i + 1) % matches.length); }
      else if (e.key === "ArrowUp") { take(); setActive((i) => (i - 1 + matches.length) % matches.length); }
      else if (e.key === "Enter" || e.key === "Tab") { take(); onPick(matches[active].handle); }
      else if (e.key === "Escape") { take(); onDismiss(); }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [matches, active, onPick, onDismiss]);

  if (matches.length === 0) return null;

  return (
    <div className={s.mentionMenu} ref={listRef} role="listbox" aria-label="Mention a teammate">
      {matches.map((m, i) => (
        <button key={m.user_id} role="option" aria-selected={i === active}
          className={`${s.mentionItem} ${i === active ? s.mentionItemOn : ""}`}
          onMouseEnter={() => setActive(i)}
          onMouseDown={(e) => { e.preventDefault(); onPick(m.handle); }}>
          <span className={s.mentionAvatar} style={{ background: colorFor(m.email) }}>
            {initialOf(m.email)}
          </span>
          <span className={s.mentionHandle}>@{m.handle}</span>
          <span className={s.mentionEmail}>{m.email}</span>
        </button>
      ))}
    </div>
  );
}
