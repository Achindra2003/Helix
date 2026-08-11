import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSession, useActiveWorkspace, useEffectiveRole } from "@/store/session";
import { useNotifications, useUnreadCount } from "@/store/notifications";
import { listNotices, markNoticesRead } from "@/lib/api";
import { onRoomEvent } from "@/lib/realtime";
import type { ServerNotice } from "@/lib/types";
import { usePresence } from "@/hooks/usePresence";
import { ROLE_META, ROLE_RANK } from "@/lib/rbac";
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
  const sessionUnread = useUnreadCount();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Two sources, and they are different in kind. The session store holds what
  // happened while you were on another tab — a run finishing, a thread being
  // concluded — and dies with the page, which is honest for events that were
  // only ever ambient. The server holds what someone asked *you*, which has to
  // survive you closing the laptop or the ask never happened.
  const [server, setServer] = useState<ServerNotice[]>([]);
  const refresh = () => listNotices().then((r) => setServer(r.notices)).catch(() => {});
  useEffect(() => { refresh(); }, []);
  // A mention arriving over the room socket while the tab is open should land
  // now, not on the next reload.
  useEffect(() => onRoomEvent((ev: any) => {
    if (ev.kind === "notice.created") refresh();
  }), []);

  const unread = sessionUnread + server.filter((n) => !n.read).length;

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
      if (!v) {
        markAllRead();
        // Opening the panel *is* having seen them; acknowledging each one
        // separately would make the bell a to-do list.
        if (server.some((n) => !n.read)) {
          markNoticesRead()
            .then(() => setServer((xs) => xs.map((n) => ({ ...n, read: true }))))
            .catch(() => {});
        }
      }
      return !v;
    });
  }

  return (
    <div className={s.bellWrap} ref={wrapRef}>
      <button className={s.bellBtn} title="What you missed" aria-label="What you missed" onClick={toggle}>
        ◷
        {unread > 0 && <span className={s.bellBadge}>{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div className={s.bellPanel}>
          <div className={s.bellHead}>
            <span className="eyebrow">While you were elsewhere</span>
            {items.length > 0 && (
              <button className="mono" style={{ border: 0, background: "transparent", cursor: "pointer", fontSize: 10, color: "var(--ink-3)" }}
                onClick={clear}>clear</button>
            )}
          </div>
          {items.length === 0 && server.length === 0 && (
            <div className={s.bellEmpty}>Nothing yet — mentions and teammates' finished runs land here.</div>
          )}
          {/* Someone asked you something. These come first and stay after a
              reload, because a request from a person outranks an event. */}
          {server.map((n) => (
            <button key={n.id} className={`${s.bellItem} ${n.read ? "" : s.bellItemUnread}`}
              onClick={() => {
                setOpen(false);
                nav(`/w/${n.workspace_id}?conv=${n.conversation_id}`);
              }}>
              <div>
                <b>{n.actor_email.split("@")[0]}</b> mentioned you
              </div>
              <div style={{ color: "var(--ink-3)", marginTop: 2 }}>{n.excerpt}</div>
              <div className="mono" style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 2 }}>
                {n.created_at ? new Date(n.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}
              </div>
            </button>
          ))}
          {items.map((n) => (
            <button key={n.id} className={`${s.bellItem} ${n.read ? "" : s.bellItemUnread}`}
              onClick={() => {
                setOpen(false);
                if (n.conversationId && ws) nav(`/w/${ws.id}?conv=${n.conversationId}`);
              }}>
              <div>{n.text}</div>
              <div className="mono" style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 2 }}>{n.time}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Your role, and the way to look at the workspace as someone with less access.
 *
 * This was four controls in the top bar: a badge naming the current role, then
 * one bare-sigil button per role beside it — ◆ ◇ ○, three near-identical marks,
 * unlabelled, in the most valuable strip in the product, for a feature an owner
 * uses about twice. It is one chip now, and the menu says what the feature is
 * rather than leaving three shapes to imply it.
 *
 * Preview only ever looks down: a role above your own is not offered, because
 * it cannot be granted and the controls it would paint are ones the server
 * refuses anyway.
 */
function RoleChip({
  role, realRole, onPreview,
}: { role: Role; realRole: Role; onPreview: (r: Role | null) => void }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const previewing = role !== realRole;

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const offered = ROLES.filter((r) => ROLE_RANK[r] <= ROLE_RANK[realRole]);

  return (
    <div className={s.roleWrap} ref={wrapRef}>
      <button
        className={`${s.badge} ${previewing ? s.badgePreview : ""}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        title={previewing
          ? `You are ${ROLE_META[realRole].label}, looking at this as ${ROLE_META[role].label}`
          : `Your role in this workspace: ${ROLE_META[role].label}`}
      >
        <span aria-hidden>{ROLE_META[role].sigil}</span>
        {/* While previewing, the chip stops naming a role and starts naming a
            state — an owner who forgets they are in preview reads missing
            buttons as a broken app. */}
        <span style={{ fontWeight: 600 }}>
          {previewing ? `Viewing as ${ROLE_META[role].label}` : ROLE_META[role].label}
        </span>
        {offered.length > 1 && <span className={s.badgeCaret} aria-hidden>⌄</span>}
      </button>

      {open && offered.length > 1 && (
        <div className={s.roleMenu} role="menu">
          <div className={s.roleMenuHead}>See it as</div>
          {offered.map((r) => (
            <button key={r} role="menuitemradio" aria-checked={role === r}
              className={`${s.roleItem} ${role === r ? s.roleItemOn : ""}`}
              onClick={() => { onPreview(r === realRole ? null : r); setOpen(false); }}>
              <span className={s.roleItemMark} aria-hidden>{ROLE_META[r].sigil}</span>
              <span className={s.roleItemLabel}>
                {ROLE_META[r].label}{r === realRole ? " — your role" : ""}
              </span>
            </button>
          ))}
          <p className={s.roleNote}>
            Preview only changes what <em>you</em> see, so you can check what a
            teammate is offered before you invite them. Nothing changes for them,
            and the server enforces the real role either way.
          </p>
        </div>
      )}
    </div>
  );
}

export function TopBar({ viewLabel }: { viewLabel: string }) {
  const ws = useActiveWorkspace();
  const role = useEffectiveRole();
  const setRolePreview = useSession((st) => st.setRolePreview);
  // The role the server actually recorded, as opposed to what is being
  // previewed. Preview can only look *down* from here.
  const realRole = ws?.role ?? "observer";
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
        <span className="mono" style={{ fontSize: 11, color: live ? "var(--ink-3)" : "var(--ember)", marginLeft: 12 }}>
          {live ? `${members.length} online · live` : "offline"}
        </span>
      </div>
      <div className={s.sep} />
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <Bell />
        <ThemeToggle />
        <RoleChip role={role} realRole={realRole} onPreview={setRolePreview} />
      </div>
    </div>
  );
}
