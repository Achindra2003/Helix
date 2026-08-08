import type { Branch } from "@/lib/types";
import { activatable } from "@/lib/a11y";
import { ACTION } from "@/lib/glyphs";
import s from "./chat.module.css";

// Depth from parent links so the lineage indents like a Git tree.
function depthOf(b: Branch, byId: Map<string, Branch>): number {
  let d = 0, cur: Branch | undefined = b;
  while (cur?.parent_branch_id) { cur = byId.get(cur.parent_branch_id); d++; if (d > 12) break; }
  return d;
}

// A resolved exploration reads differently at a glance: adopted keeps full
// contrast and gains a seal, abandoned recedes without disappearing. Nothing
// is ever hidden — the rejected alternative is half of why the adopted one is
// defensible, so it stays in the lineage, just quieter.
const MARK: Record<Branch["status"], { glyph: string; color: string; label: string } | null> = {
  open: null,
  adopted: { glyph: "✓", color: "var(--verde)", label: "adopted" },
  abandoned: { glyph: "✕", color: "var(--ink-faint)", label: "abandoned" },
};

export function BranchTree({
  branches, activeId, meId, onSelect, onRename, onDelete, onResolve, onVote,
}: {
  branches: Branch[];
  activeId: string | null;
  // Who "you" are, so the tally can show whether you have already backed a
  // branch. Without it the count is a number you cannot locate yourself in.
  meId?: string;
  onSelect: (id: string) => void;
  // Fork-branch housekeeping (Collaborator+). Main never shows these; the
  // server additionally refuses deleting anything something forked from.
  onRename?: (b: Branch) => void;
  onDelete?: (b: Branch) => void;
  // Recording what came of an exploration — offered on every branch including
  // main, because the spine can be the thing you adopted.
  onResolve?: (b: Branch) => void;
  // Backing an exploration: the cheap signal that precedes the verdict.
  onVote?: (b: Branch) => void;
}) {
  const byId = new Map(branches.map((b) => [b.id, b]));
  // A tally only means something against alternatives. On a thread that never
  // forked there is nothing to converge, so the control would be an instruction
  // to weigh one option against itself.
  const converging = branches.length > 1;
  return (
    <>
      <div className={s.divider} />
      <div className={s.lineHead}>
        <span style={{ color: "var(--oxblood)", fontSize: 14 }} aria-hidden>{ACTION.fork}</span>
        <span className="eyebrow">Branch lineage</span>
      </div>
      {branches.map((b) => {
        const on = b.id === activeId;
        const depth = depthOf(b, byId);
        const fork = b.parent_branch_id !== null;
        const mark = MARK[b.status];
        const resolved = b.status !== "open";
        const votes = b.votes ?? [];
        const tally = votes.length;
        const backing = !!meId && votes.includes(meId);
        // The intent is what this exploration set out to try; the resolution is
        // what came of it. Together they're the whole record, so the title
        // attribute carries both for the row.
        const title = [
          b.intent && `Trying: ${b.intent}`,
          resolved && b.resolution && `${mark?.label}: ${b.resolution}`,
        ].filter(Boolean).join("\n") || undefined;
        return (
          <div key={b.id}>
          {/* The row stays a plain clickable container so the whole strip is
              still a mouse target. The keyboard and screen-reader entry point
              is the branch name below — putting it here would make ARIA treat
              this row's contents as presentational and hide the resolve,
              rename and delete buttons along with the verdict mark. */}
          <div
            className={`${s.branchRow} ${on ? s.branchOn : ""}`}
            title={title}
            onClick={() => onSelect(b.id)}
          >
            <span className="mono" style={{ fontSize: 12, color: "var(--ink-faint)", width: depth * 14, display: "inline-block", textAlign: "right" }}>
              {depth ? "└" : ""}
            </span>
            <span className={s.branchDot} style={{ background: on ? "var(--oxblood)" : "var(--ink-faint)", boxShadow: on ? "0 0 0 3px rgba(143,62,19,0.16)" : "none" }} />
            <span
              className={s.branchName}
              aria-current={on ? "true" : undefined}
              style={{
                color: on ? "var(--ink)" : "var(--ink-3)",
                flex: 1,
                minWidth: 0,
                // Abandoned recedes; it is still selectable and still readable.
                opacity: b.status === "abandoned" ? 0.6 : 1,
                textDecoration: b.status === "abandoned" ? "line-through" : undefined,
              }}
              {...activatable(() => onSelect(b.id))}
            >
              {b.name}
            </span>
            {mark && (
              <span className={s.branchMark} aria-label={mark.label} style={{ color: mark.color }}>
                {mark.glyph}
              </span>
            )}
            {/* aria-label, not just title: the button's own text is a glyph,
                and text content wins the accessible-name computation — so
                without these these announce as "⚖", "✎", "✕". Now that the
                row beside them is reachable by keyboard, arriving at three
                unnamed buttons would be a half-fix of the same journey. */}
            {/* Outside `.branchActs`, which is hover-only. Backing is a
                standing fact about the branch, not an action you go looking
                for: a tally you can only see by hovering each row in turn
                cannot be scanned, and scanning is the entire use — "which of
                these four does the team actually want". So a backed branch
                always shows its count, and an unbacked one offers the verb on
                hover.

                Words, not a mark: the inventory has no glyph for "I'd back
                this", and inventing one would put an unreadable symbol at 11px
                beside three established ones. `aria-pressed` because this is a
                toggle — a screen reader should say whether you are in. */}
            {converging && onVote && (
              <button
                className={`${s.branchVote} ${backing ? s.branchVoteOn : ""} ${tally ? s.branchVoteShown : ""}`}
                aria-pressed={backing}
                title={
                  backing
                    ? "You're backing this — click to withdraw"
                    : "Back this exploration"
                }
                aria-label={`${backing ? "Withdraw backing from" : "Back"} ${b.name}`}
                onClick={(e) => { e.stopPropagation(); onVote(b); }}
              >
                {backing ? "backing" : "back"}{tally ? ` · ${tally}` : ""}
              </button>
            )}
            <span className={s.branchActs}>
              {onResolve && (
                <button className={`icon-act ${s.branchAct}`}
                  title={resolved ? "Change the verdict" : "Record what came of this"}
                  aria-label={`${resolved ? "Change the verdict on" : "Record what came of"} ${b.name}`}
                  onClick={(e) => { e.stopPropagation(); onResolve(b); }}>⚖</button>
              )}
              {fork && onRename && (
                <button className={`icon-act ${s.branchAct}`} title="Rename branch"
                  aria-label={`Rename ${b.name}`}
                  onClick={(e) => { e.stopPropagation(); onRename(b); }}>✎</button>
              )}
              {fork && onDelete && (
                <button className={`icon-act ${s.branchAct}`} style={{ color: "var(--oxblood)" }}
                  title="Delete branch"
                  aria-label={`Delete ${b.name}`}
                  onClick={(e) => { e.stopPropagation(); onDelete(b); }}>✕</button>
              )}
            </span>
          </div>
          {resolved && b.resolution && (
            <div
              className={s.branchWhy}
              style={{ marginLeft: depth * 14 + 16 }}
              title={b.resolution}
            >
              {b.resolution}
            </div>
          )}
          </div>
        );
      })}
    </>
  );
}
