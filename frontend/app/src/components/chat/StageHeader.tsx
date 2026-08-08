// What you are reading, and what the team has already settled about it.
//
// This header is where the product's convergence claim is cashed: above the
// transcript sits the thread's conclusion, the verdict on this particular
// branch, and what that branch was trying — so a person arriving late learns
// "this was abandoned three days ago, and here is why" before they spend an
// afternoon redoing it. That is the whole argument, and it was a hundred lines
// of JSX buried two thirds of the way down a 1,300-line view.
//
// Purely presentational: every action arrives as a callback, so this file can
// be read start to finish without knowing how a fork or a conclusion is saved.
import type { Branch, Conversation, ConversationRef } from "@/lib/types";
import { Button } from "@/components/common/Button";
import { ThreadMenu, type ThreadAction } from "@/components/chat/ThreadMenu";
import { STATE } from "@/lib/glyphs";
import s from "@/components/chat/chat.module.css";

export function StageHeader({
  conversation, branch, references, messageCount, canSend, canFork,
  threadActions, onConclude, onResolve, onFork, onUnlinkRef, onOpenLedger,
}: {
  conversation: Conversation;
  branch: Branch | null | undefined;
  references: ConversationRef[];
  messageCount: number;
  canSend: boolean;
  canFork: boolean;
  threadActions: ThreadAction[];
  onConclude: () => void;
  onResolve: (branch: Branch) => void;
  onFork: () => void;
  onUnlinkRef: (refId: string) => void;
  /** The ledger of every decision in the workspace. */
  onOpenLedger: () => void;
}) {
  return (
    <div className={s.stageHead}>
      <div className={s.stageTitleBlock}>
        {/* The title alone. Rename and delete already exist on the
            conversation row in the thread list, and now also in the
            thread menu — three copies of one action was two too many,
            and they were squeezing the one thing this header must
            always show. */}
        <div className={s.stageTitle}>
          <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", display: "block" }}>
            {conversation.title}
          </span>
        </div>
        <div className={s.stageMeta}>
          <span className={s.chip} style={{ color: conversation.visibility === "private" ? "var(--ink-3)" : "var(--oxblood)" }}>
            {/* The word alone. ◍ / ⊙ prefixed it here, in the thread list and
                on the Map — two circles nobody can tell apart at 11px, in
                front of the word that already said it. */}
            {conversation.visibility === "private" ? "private" : "shared"}
          </span>
          <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>
            on <span style={{ color: "var(--oxblood)" }}>{branch?.name ?? "main"}</span>
          </span>
          <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{messageCount} nodes</span>
        </div>
        {/* What the thread concluded, above the branch verdict: it is
            the answer to the question the whole conversation was
            asking, so it outranks the fate of any one exploration. */}
        {conversation.conclusion && (
          <div className={s.conclusion}>
            <span className={s.conclusionLabel}>
              <button className={s.toLedger} onClick={onOpenLedger}
                title="Everything this team has decided, and why">Concluded</button>
            </span>
            <span>{conversation.conclusion}</span>
            {canSend && (
              <button className={`icon-act ${s.branchAct}`} style={{ opacity: 0.7 }}
                title="Revise the conclusion" onClick={onConclude}>✎</button>
            )}
          </div>
        )}
        {/* The verdict on the branch you are reading. Above the linked
            context because "this was abandoned three days ago, and
            here is why" outranks everything else in this header — it
            is the difference between continuing useful work and
            redoing something the team already rejected. */}
        {branch && branch.status !== "open" && (
          <div className={s.branchVerdict} data-status={branch.status}>
            <span className={s.verdictMark}>
              {branch.status === "adopted" ? "✓" : "✕"}
            </span>
            <span>
              <b>
                <button className={s.toLedger} onClick={onOpenLedger}
                  title="Everything this team has decided, and why">
                  {branch.status === "adopted" ? "Adopted" : "Abandoned"}
                </button>
              </b>
              {branch.resolution && <> — {branch.resolution}</>}
              {branch.intent && (
                <span className={s.verdictIntent}> · was trying: {branch.intent}</span>
              )}
            </span>
            {canFork && (
              <button className={`icon-act ${s.branchAct}`} style={{ opacity: 0.7 }}
                title="Change the verdict"
                onClick={() => onResolve(branch)}>⚖</button>
            )}
          </div>
        )}
        {/* Only when something IS linked. The "＋ link context" button
            lived here permanently to offer an action most threads never
            use; it is in the thread menu now, and this row went back to
            being what it says it is — a list of what this thread draws
            on. */}
        {references.length > 0 && (
          <div className={s.stageMeta} style={{ marginTop: 6, flexWrap: "wrap" }}>
            <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>linked context:</span>
            {references.map((r) => (
              <span key={r.id} className={s.chip} title="Replies here draw on this thread's live context"
                style={{ color: "var(--ink-2)", display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span aria-hidden>{STATE.linked}</span> {r.title}
                {canSend && (
                  <button onClick={() => onUnlinkRef(r.id)} title="Unlink"
                    style={{ border: 0, background: "transparent", cursor: "pointer", color: "var(--ink-3)", fontSize: 13, lineHeight: 1, padding: 0 }}>×</button>
                )}
              </span>
            ))}
          </div>
        )}
      </div>
      <ThreadMenu actions={threadActions} />
      {canSend && messageCount > 0 && !conversation.conclusion && (
        <Button onClick={onConclude} title="Say what this thread concluded">
          <span style={{ color: "var(--verde)" }}>❧</span> Conclude
        </Button>
      )}
      {canFork && (
        <Button onClick={onFork}>
          <span style={{ color: "var(--oxblood)" }}>⌇</span> Fork
        </Button>
      )}
    </div>
  );
}
