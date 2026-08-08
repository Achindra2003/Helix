import type { WorkspaceSearchHit } from "@/lib/types";
import { colorFor } from "@/lib/format";
import { PLACE } from "@/lib/glyphs";
import s from "./chat.module.css";

export interface RoomDraft {
  email: string;
  where: { id: string; title: string };
  match: { id: string; title: string } | null;
}

/**
 * One strip above the composer, answering one question: **has the team been
 * here?** — in its two tenses.
 *
 * NOW: a teammate's turn streaming into this branch, or a teammate composing a
 * question somewhere that overlaps yours.
 * BEFORE: threads that already explored what you are typing.
 *
 * These were three separate banners that could stack three-deep in the same
 * strip of space, each with its own border, competing for the same glance. They
 * are not three subjects; they are one subject at three distances. A single
 * bordered surface with quiet rows inside it says that, and stops the composer
 * being shoved down the screen by whichever combination happens to fire.
 *
 * The approval banner deliberately stays separate — it is not information about
 * the team, it is a decision the run is blocked on.
 */
export function TeamStrip({
  liveAuthor, drafts, explored, canSend, onOpen, onLinkFor, onMute, whoOf,
}: {
  liveAuthor: string | null;
  drafts: RoomDraft[];
  explored: WorkspaceSearchHit[];
  canSend: boolean;
  onOpen: (conversationId: string, branchId?: string) => void;
  onLinkFor: (targetConversationId: string, referenceId: string) => void;
  onMute: () => void;
  /** Resolves a hit's author to "you" / an email / "a teammate". */
  whoOf: (hit: WorkspaceSearchHit) => string;
}) {
  const showExplored = canSend && explored.length > 0;
  if (!liveAuthor && drafts.length === 0 && !showExplored) return null;

  return (
    <div className={s.teamStrip}>
      {liveAuthor && (
        <div className={s.teamRow}>
          <span className={s.rowDot} style={{ background: colorFor(liveAuthor) }} />
          <span className={s.teamWho}>{liveAuthor}</span>
          <span className={s.teamSays}>is asking Helix…</span>
        </div>
      )}

      {drafts.map((d) => (
        <div key={d.email} className={s.teamRow}>
          <span className={s.rowDot} style={{ background: colorFor(d.email) }} />
          <span className={s.teamWho}>{d.email}</span>
          <span className={s.teamSays}>is drafting in</span>
          <button className={s.chip} title="Open their thread"
            onClick={() => onOpen(d.where.id)}
            style={{ cursor: "pointer", color: "var(--ink-2)", maxWidth: 220 }}>
            <span className={s.teamClip}>{d.where.title}</span>
          </button>
          {d.match && (
            // One group, so the arrow never wraps away from the thread it
            // points at.
            <span className={s.teamGroup}>
              <span style={{ color: "var(--gilt)", flex: "0 0 auto" }}>↳ overlaps</span>
              <button className={s.chip} title="Open the thread it overlaps"
                onClick={() => onOpen(d.match!.id)}
                style={{ cursor: "pointer", color: "var(--ink-2)", maxWidth: 220 }}>
                <span className={s.teamClip}>{d.match.title}</span>
              </button>
              {canSend && (
                <button className={s.chip} title="Add that thread as linked context on theirs, before they send"
                  onClick={() => onLinkFor(d.where.id, d.match!.id)}
                  style={{ cursor: "pointer", border: "1px dashed var(--rule-soft)", background: "transparent", color: "var(--oxblood)" }}>
                  link it for them
                </button>
              )}
            </span>
          )}
        </div>
      ))}

      {showExplored && (
        <div className={s.teamRow}>
          <span style={{ color: "var(--gilt)", flex: "0 0 auto" }}>✦</span>
          <span className={s.teamSays}>explored before —</span>
          {explored.map((h) => (
            <button key={h.node_id} className={s.chip}
              title={`${whoOf(h)}: “${h.excerpt}”`}
              onClick={() => onOpen(h.conversation_id, h.branch_id)}
              style={{ cursor: "pointer", color: "var(--ink-2)", maxWidth: 260 }}>
              <span style={{ color: "var(--oxblood)" }} aria-hidden>{PLACE.chat}</span>
              <span className={s.teamClip}>{h.conversation_title}</span>
              <span style={{ color: "var(--ink-3)", flex: "0 0 auto" }}>· {whoOf(h)}</span>
            </button>
          ))}
          <div style={{ flex: 1 }} />
          <button className={s.teamMute} onClick={onMute} title="Dismiss for this question">×</button>
        </div>
      )}
    </div>
  );
}
