import { initialOf } from "@/lib/format";
import s from "./chat.module.css";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  authorName: string;
  body: string;
  time: string;
  tokens?: string;
  typing?: boolean;
  forkPoint?: boolean;
}

function Bubble({ m, onForkHere }: { m: ChatMessage; onForkHere?: (id: string) => void }) {
  const asst = m.role === "assistant";
  return (
    <div className={s.msg}>
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
          {onForkHere && !m.typing && (
            <button className={s.forkHere} title="Fork a new branch from here" onClick={() => onForkHere(m.id)}>
              ⌇ fork here
            </button>
          )}
        </div>
        <div className={s.msgBody}>
          {m.body}
          {m.typing && <span className={s.cursor} />}
        </div>
        {m.tokens && <div className={s.msgTokens}>{m.tokens}</div>}
      </div>
    </div>
  );
}

export function MessageList({ messages, onForkHere }: { messages: ChatMessage[]; onForkHere?: (id: string) => void }) {
  return (
    <>
      {messages.map((m) => (
        <Bubble key={m.id} m={m} onForkHere={onForkHere} />
      ))}
    </>
  );
}
