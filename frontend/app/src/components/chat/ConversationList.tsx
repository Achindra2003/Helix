import type { Conversation } from "@/lib/types";
import s from "./chat.module.css";

export function ConversationList({
  conversations, activeId, canCreate, onSelect, onNew,
}: {
  conversations: Conversation[];
  activeId: string | null;
  canCreate: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  return (
    <>
      <div className={s.leftHead}>
        <span className="eyebrow">Conversations</span>
        {canCreate && <button className={s.plus} title="New conversation" onClick={onNew}>+</button>}
      </div>
      <div>
        {conversations.map((c) => (
          <div key={c.id} className={`${s.convRow} ${c.id === activeId ? s.convOn : ""}`} onClick={() => onSelect(c.id)}>
            <span style={{ fontSize: 13, color: c.visibility === "private" ? "var(--ink-3)" : "var(--oxblood)", marginTop: 1 }}>
              {c.visibility === "private" ? "◍" : "⊙"}
            </span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className={s.convTitle} style={{ fontWeight: c.id === activeId ? 600 : 400 }}>{c.title}</div>
              <div className={s.convMeta}>{c.visibility}</div>
            </div>
          </div>
        ))}
        {conversations.length === 0 && (
          <div style={{ padding: "8px 10px", color: "var(--ink-faint)", fontStyle: "italic", fontSize: 13 }}>
            No conversations yet.
          </div>
        )}
      </div>
    </>
  );
}
