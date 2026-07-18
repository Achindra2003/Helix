import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSession, useActiveWorkspace, useEffectiveRole } from "@/store/session";
import { useNotifications, useUnreadCount } from "@/store/notifications";
import { usePresence } from "@/hooks/usePresence";
import { ROLE_META } from "@/lib/rbac";
import { initialOf, colorFor } from "@/lib/format";
import type { Role } from "@/lib/types";
import { ThemeToggle } from "@/components/common/ThemeToggle";
import s from "./shell.module.css";

const ROLES: Role[] = ["owner", "collaborator", "observer"];

function Bell() {
  const nav = useNavigate();
  const ws = useActiveWorkspace();
  const items = useNotifications((st) => st.items);
  const markAllRead = useNotifications((st) => st.markAllRead);
  const clear = useNotifications((st) => st.clear);
  const unread = useUnreadCount();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Close on outside click; opening the panel marks everything read.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open]);

  function toggle() {
    setOpen((v) => {
      if (!v) markAllRead();
      return !v;
    });
  }

  return (
    <div className={s.bellWrap} ref={wrapRef}>
      <button className={s.bellBtn} title="Notifications (this session)" onClick={toggle}>
        ◷
        {unread > 0 && <span className={s.bellBadge}>{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div className={s.bellPanel}>
          <div className={s.bellHead}>
            <span className="eyebrow">While you were elsewhere</span>
            {items.length > 0 && (
              <button className="mono" style={{ border: 0, background: "transparent", cursor: "pointer", fontSize: 10.5, color: "var(--ink-3)" }}
                onClick={clear}>clear</button>
            )}
          </div>
          {items.length === 0 && <div className={s.bellEmpty}>Nothing yet — teammates' deep runs land here when they finish.</div>}
          {items.map((n) => (
            <button key={n.id} className={`${s.bellItem} ${n.read ? "" : s.bellItemUnread}`}
              onClick={() => {
                setOpen(false);
                if (n.conversationId && ws) nav(`/w/${ws.id}?conv=${n.conversationId}`);
              }}>
              <div>{n.text}</div>
              <div className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)", marginTop: 2 }}>{n.time}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function TopBar({ viewLabel }: { viewLabel: string }) {
  const ws = useActiveWorkspace();
  const role = useEffectiveRole();
  const setRolePreview = useSession((st) => st.setRolePreview);
  const { members, live } = usePresence(ws?.id ?? null);

  return (
    <div className={s.topbar}>
      <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
        <div className={s.wsMark}>{(ws?.name ?? "·").charAt(0).toUpperCase()}</div>
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.15 }}>
          <span className={s.wsName}>{ws?.name ?? "Workspace"}</span>
          <span className={s.wsSub}>{viewLabel}</span>
        </div>
      </div>
      <div className={s.spacer} />
      <div className={s.presence} title={live ? `online now: ${members.map((m) => m.email).join(", ")}` : "reconnecting to the workspace room…"}>
        {members.slice(0, 5).map((m) => (
          <div key={m.user_id} className={s.pAvatar} style={{ background: colorFor(m.email) }} title={m.email}>
            {initialOf(m.email)}
          </div>
        ))}
        <span className="mono" style={{ fontSize: 11.5, color: live ? "var(--ink-3)" : "var(--ember)", marginLeft: 12 }}>
          {live ? `${members.length} online · live` : "offline"}
        </span>
      </div>
      <div className={s.sep} />
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <Bell />
        <ThemeToggle />
        <div className={s.badge}><span>{ROLE_META[role].sigil}</span><span style={{ fontWeight: 600 }}>{ROLE_META[role].label}</span></div>
        <div className={s.roleSw} title="Preview the workspace as each role">
          {ROLES.map((r) => (
            <button key={r} className={role === r ? s.swOn : s.swBtn} title={`View as ${ROLE_META[r].label}`}
              onClick={() => setRolePreview(r)}>{ROLE_META[r].sigil}</button>
          ))}
        </div>
      </div>
    </div>
  );
}
