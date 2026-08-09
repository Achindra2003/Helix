import { initialOf } from "@/lib/format";
import { Markdown } from "@/components/common/Markdown";
import type { GroundingItem } from "@/lib/types";
import { ACTION, PLACE, STATE } from "@/lib/glyphs";
import s from "./chat.module.css";

// One tool call in an agent turn (FR-14): requested → (approval?) → resolved.
// "pending" = a sensitive call holding for a human verdict.
export interface ToolActivity {
  id: string;
  name: string;
  args: string; // compact one-line rendering of the arguments
  sensitive: boolean;
  status: "running" | "pending" | "ok" | "error" | "denied";
  preview?: string; // the tool_result's content preview
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "note";
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
  // Agent tool ledger — what the model did before it answered (stream-only,
  // like grounding: nodes don't persist it, this session's memory does).
  tools?: ToolActivity[];
  // The technical reason a run failed, when one did. Shown as a small aside
  // under the plain-language message rather than *as* the message: a reader
  // cannot act on a Python exception, but the person they forward it to can.
  error?: string;
}

/** Marks the `@handles` in a note so the person addressed can find their own
 *  name by scanning. Cosmetic only — the server already decided who was
 *  actually notified, and a handle nobody matched is left looking like what it
 *  is: ordinary text that reached no one. */
function withMentions(text: string) {
  const parts = text.split(/(@[A-Za-z0-9._%+-]+)/g);
  return parts.map((p, i) =>
    p.startsWith("@") && p.length > 1
      ? <span key={i} className={s.mentionTag}>{p}</span>
      : p,
  );
}

const TOOL_GLYPH: Record<ToolActivity["status"], { glyph: string; color: string; label: string }> = {
  running: { glyph: STATE.running, color: "var(--gilt)", label: "running" },
  pending: { glyph: STATE.waiting, color: "var(--gilt)", label: "awaiting approval" },
  ok: { glyph: ACTION.confirm, color: "var(--verde)", label: "done" },
  error: { glyph: ACTION.remove, color: "var(--oxblood)", label: "failed" },
  denied: { glyph: STATE.denied, color: "var(--ink-3)", label: "denied" },
};

// Delete/edit is only ever offered on the branch's *trailing* turn you wrote
// (edit = delete + resend; history stays append-only underneath).
export interface LastTurnActions {
  userMsgId: string;
  onDelete: () => void;
  onEdit: () => void;
}

function Bubble({ m, dropCap, onForkHere, onExploreHere, lastTurn }: {
  m: ChatMessage; dropCap?: boolean;
  onForkHere?: (id: string) => void; onExploreHere?: (id: string) => void;
  lastTurn?: LastTurnActions;
}) {
  // A note is one person talking to the room, not to Helix — so it is not a
  // bubble at all. It sits in the margin like a hand-written annotation,
  // keeping its place in the thread without pretending to be a turn.
  if (m.role === "note") {
    // (see withMentions below)
    return (
      <div className={s.note} style={{ borderLeftColor: m.authorColor ?? "var(--ink-faint)" }}>
        <span className={s.noteWho} style={{ color: m.authorColor }}>{m.authorName}</span>
        <span className={s.noteBody}>{withMentions(m.body)}</span>
        <span className={s.noteAside} title="Notes are for your teammates — Helix never reads them">
          to the team
        </span>
      </div>
    );
  }
  const asst = m.role === "assistant";
  const mine = lastTurn?.userMsgId === m.id;
  return (
    <div
      className={`${s.msg} ${s.msgQuill}`}
      style={{ borderLeftColor: !asst && m.authorColor ? m.authorColor : "transparent" }}
    >
      <div className={`${s.avatar} ${asst ? s.avatarAsst : s.avatarUser} ${asst && m.typing ? s.avatarThinking : ""}`}>
        {asst ? "⟳" : initialOf(m.authorName)}
      </div>
      <div className={asst ? s.leaf : s.userBody} style={{ minWidth: 0, flex: 1 }}>
        <div className={s.msgHead}>
          <span className={s.msgName} style={{ color: asst ? "var(--oxblood)" : "var(--ink)" }}>
            {asst ? "Helix" : m.authorName}
          </span>
          {m.time && <span className={s.msgTime}>{m.time}</span>}
          {m.forkPoint && <span className={s.forkTag}>{ACTION.fork} fork point</span>}
          {m.forkChildren && m.forkChildren.length > 0 && (
            <span className={s.forkMark} title={`branches from here: ${m.forkChildren.join(", ")}`}>
              {ACTION.fork} {m.forkChildren[0]}{m.forkChildren.length > 1 ? ` +${m.forkChildren.length - 1}` : ""}
            </span>
          )}
          {onForkHere && !m.typing && (
            <button className={s.forkHere} title="Fork a new branch from here" onClick={() => onForkHere(m.id)}>
              {ACTION.fork} fork here
            </button>
          )}
          {/* The other half of what a branch is for. One fork is a commitment
              worth naming; four are a brainstorm, and naming each one is the
              ceremony that made divergence expensive. */}
          {onExploreHere && !m.typing && (
            <button className={s.forkHere} title="Explore several angles from here, side by side"
              onClick={() => onExploreHere(m.id)}>
              {ACTION.fork} explore ways
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
        {m.tools && m.tools.length > 0 && (
          <div className={s.toolLedger}>
            {m.tools.map((t) => {
              const g = TOOL_GLYPH[t.status];
              return (
                <div key={t.id || t.name} className={s.toolRow}
                  title={t.preview ? `${g.label} — ${t.preview}` : g.label}>
                  <span className={s.toolStatus} style={{ color: g.color }}>{g.glyph}</span>
                  <span style={{ color: "var(--oxblood)" }}>{ACTION.agent} {t.name}</span>
                  {t.args && <span className={s.toolArgs}>({t.args})</span>}
                  {t.status === "pending" && <span style={{ color: "var(--gilt)" }}>awaiting approval</span>}
                  {t.status === "denied" && <span style={{ color: "var(--ink-3)" }}>denied</span>}
                </div>
              );
            })}
          </div>
        )}
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
            {/* The catalogued reference where the document has one — "Smith et
                al. (2019) §4" rather than "smith-et-al-final-v3.pdf §4", which
                named a file on somebody's laptop rather than a work. The
                filename stays in the tooltip: it is still what you open. */}
            {m.grounding.map((g, i) => (
              <span key={`${g.document_id}-${g.chunk_index}-${i}`} className={s.groundChip}
                title={`${g.cite_as && g.cite_as !== g.filename ? `${g.filename} · ` : ""}relevance ${g.score.toFixed(2)} — “${g.excerpt}”`}>
                {PLACE.docs} {g.cite_as || g.filename} §{g.chunk_index + 1}
              </span>
            ))}
          </div>
        )}
        {m.error && (
          <div className={s.runError} title="What the server reported">
            {m.error}
          </div>
        )}
        {m.tokens && <div className={s.colophon}>❧ {m.tokens} ❧</div>}
      </div>
    </div>
  );
}

export function MessageList({ messages, onForkHere, onExploreHere, lastTurn }: {
  messages: ChatMessage[];
  onForkHere?: (id: string) => void; onExploreHere?: (id: string) => void;
  lastTurn?: LastTurnActions;
}) {
  // The thread's first assistant reply opens with a drop cap, like the first
  // page of a chapter.
  const firstAsst = messages.findIndex((m) => m.role === "assistant");
  return (
    <>
      {messages.map((m, i) => (
        <Bubble key={m.id} m={m} dropCap={i === firstAsst} onForkHere={onForkHere}
          onExploreHere={onExploreHere} lastTurn={lastTurn} />
      ))}
    </>
  );
}
