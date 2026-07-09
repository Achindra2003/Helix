import { useSession, useActiveWorkspace, useEffectiveRole } from "@/store/session";
import { usePresence } from "@/hooks/usePresence";
import { ROLE_META } from "@/lib/rbac";
import { initialOf, colorFor } from "@/lib/format";
import type { Role } from "@/lib/types";
import { ThemeToggle } from "@/components/common/ThemeToggle";
import s from "./shell.module.css";

const ROLES: Role[] = ["owner", "collaborator", "observer"];

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
