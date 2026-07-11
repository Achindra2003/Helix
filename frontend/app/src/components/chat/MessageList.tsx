import { initialOf } from "@/lib/format";
import { Markdown } from "@/components/common/Markdown";
import type { GroundingItem } from "@/lib/types";
import s from "./chat.module.css";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  authorName: string;
  // Deterministic per-author accent (colorFor(email)); paints the margin quill
  // on user turns so a multi-author thread reads at a glance. Assistant stays
  // neutral ink.
  authorColor?: string;
  body: string;
  time: string;
  tokens?: string;
  typing?: boolean;
  forkPoint?: boolean;
  // Names of branches forked *from* this message (always-visible margin glyph).
  forkChildren?: string[];
  // Knowledge-base sources this reply grounded on (the `grounding` SSE frame).
  grounding?: GroundingItem[];
}

// Delete/edit is only ever offered on the branch's *trailing* turn you wrote
// (edit = delete + resend; history stays append-only underneath).
export interface LastTurnActions {
  userMsgId: string;
  onDelete: () => void;
  onEdit: () => void;
}

function Bubble({ m, dropCap, onForkHere, lastTurn }: {
  m: ChatMessage; dropCap?: boolean; onForkHere?: (id: string) => void; lastTurn?: LastTurnActions;
}) {
  const asst = m.role === "assistant";
  const mine = lastTurn?.userMsgId === m.id;
  return (
    <div
      className={`${s.msg} ${s.msgQuill}`}
      style={{ borderLeftColor: !asst && m.authorColor ? m.authorColor : "transparent" }}
    >
      <div className={`${s.avatar} ${asst ? s.avatarAsst : s.avatarUser}`}>
        {asst ? "⟳" : initialOf(m.authorName)}
      </div>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div className={s.msgHead}>
          <span className={s.msgName} style={{ color: asst ? "var(--oxblood)" : "var(--ink)" }}>
            {asst ? "Helix" : m.authorName}
          </span>
          {m.time && <span className={s.msgTime}>{m.time}</span>}
          {m.forkPoint && <span className={s.forkTag}>⌇ fork point</span>}
          {m.forkChildren && m.forkChildren.length > 0 && (
            <span className={s.forkMark} title={`branches from here: ${m.forkChildren.join(", ")}`}>
              ⎇ {m.forkChildren[0]}{m.forkChildren.length > 1 ? ` +${m.forkChildren.length - 1}` : ""}
            </span>
          )}
          {onForkHere && !m.typing && (
            <button className={s.forkHere} title="Fork a new branch from here" onClick={() => onForkHere(m.id)}>
              ⌇ fork here
            </button>
          )}
          {mine && !m.typing && (
            <>
              <button className={s.forkHere} title="Edit and resend — removes this message (and its reply) and puts the text back in the composer"
                onClick={lastTurn!.onEdit}>
                ✎ edit
              </button>
              <button className={s.forkHere} style={{ color: "var(--oxblood)" }}
                title="Delete this message and its reply" onClick={lastTurn!.onDelete}>
                ✕ delete
              </button>
            </>
          )}
        </div>
        <div className={`${s.msgBody} ${asst && dropCap && !m.typing ? s.dropCap : ""}`}>
          {asst ? (
            <>
              <Markdown>{m.body}</Markdown>
              {m.typing && <span className={s.cursor} />}
            </>
          ) : (
            <>
              {m.body}
              {m.typing && <span className={s.cursor} />}
            </>
          )}
        </div>
        {m.grounding && m.grounding.length > 0 && (
          <div className={s.groundRow}>
            <span className={s.groundLabel}>grounded on</span>
            {m.grounding.map((g, i) => (
              <span key={`${g.document_id}-${g.chunk_index}-${i}`} className={s.groundChip}
                title={`relevance ${g.score.toFixed(2)} — “${g.excerpt}”`}>
                ⌘ {g.filename} §{g.chunk_index + 1}
              </span>
            ))}
          </div>
        )}
        {m.tokens && <div className={s.colophon}>❧ {m.tokens} ❧</div>}
      </div>
    </div>
  );
}

export function MessageList({ messages, onForkHere, lastTurn }: {
  messages: ChatMessage[]; onForkHere?: (id: string) => void; lastTurn?: LastTurnActions;
}) {
  // The thread's first assistant reply opens with a drop cap, like the first
  // page of a chapter.
  const firstAsst = messages.findIndex((m) => m.role === "assistant");
  return (
    <>
      {messages.map((m, i) => (
        <Bubble key={m.id} m={m} dropCap={i === firstAsst} onForkHere={onForkHere} lastTurn={lastTurn} />
      ))}
    </>
  );
}
