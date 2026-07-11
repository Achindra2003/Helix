import type { Branch } from "@/lib/types";
import s from "./chat.module.css";

// Depth from parent links so the lineage indents like a Git tree.
function depthOf(b: Branch, byId: Map<string, Branch>): number {
  let d = 0, cur: Branch | undefined = b;
  while (cur?.parent_branch_id) { cur = byId.get(cur.parent_branch_id); d++; if (d > 12) break; }
  return d;
}

export function BranchTree({
  branches, activeId, onSelect, onRename, onDelete,
}: {
  branches: Branch[];
  activeId: string | null;
  onSelect: (id: string) => void;
  // Fork-branch housekeeping (Collaborator+). Main never shows these; the
  // server additionally refuses deleting anything something forked from.
  onRename?: (b: Branch) => void;
  onDelete?: (b: Branch) => void;
}) {
  const byId = new Map(branches.map((b) => [b.id, b]));
  return (
    <>
      <div className={s.divider} />
      <div className={s.lineHead}>
        <span style={{ color: "var(--oxblood)", fontSize: 14 }}>⌇</span>
        <span className="eyebrow">Branch lineage</span>
      </div>
      {branches.map((b) => {
        const on = b.id === activeId;
        const depth = depthOf(b, byId);
        const fork = b.parent_branch_id !== null;
        return (
          <div key={b.id} className={`${s.branchRow} ${on ? s.branchOn : ""}`} onClick={() => onSelect(b.id)}>
            <span className="mono" style={{ fontSize: 12, color: "var(--ink-faint)", width: depth * 14, display: "inline-block", textAlign: "right" }}>
              {depth ? "└" : ""}
            </span>
            <span className={s.branchDot} style={{ background: on ? "var(--oxblood)" : "var(--ink-faint)", boxShadow: on ? "0 0 0 3px rgba(143,62,19,0.16)" : "none" }} />
            <span className={s.branchName} style={{ color: on ? "var(--ink)" : "var(--ink-3)", flex: 1, minWidth: 0 }}>{b.name}</span>
            {fork && onRename && (
              <button className={s.branchAct} title="Rename branch"
                onClick={(e) => { e.stopPropagation(); onRename(b); }}>✎</button>
            )}
            {fork && onDelete && (
              <button className={s.branchAct} style={{ color: "var(--oxblood)" }} title="Delete branch"
                onClick={(e) => { e.stopPropagation(); onDelete(b); }}>✕</button>
            )}
          </div>
        );
      })}
    </>
  );
}
