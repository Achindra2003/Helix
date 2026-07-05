import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listMembers, createInvite, setMemberRole } from "@/lib/api";
import { can, PERMISSION_ROWS, ROLE_META } from "@/lib/rbac";
import { useEffectiveRole } from "@/store/session";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Dialog } from "@/components/common/Dialog";
import { Spinner } from "@/components/common/Feedback";
import { initialOf, colorFor } from "@/lib/format";
import type { Role } from "@/lib/types";
import { ProviderPanel } from "./ProviderPanel";
import s from "./members.module.css";

const ROLES: Role[] = ["owner", "collaborator", "observer"];

export function MembersView() {
  const { wid } = useParams();
  const qc = useQueryClient();
  const { push } = useToast();
  const role = useEffectiveRole();
  const canManage = can(role, "member.manage");
  const [invite, setInvite] = useState<{ token: string; url: string } | null>(null);

  const { data: members, isLoading } = useQuery({
    queryKey: ["members", wid],
    queryFn: () => listMembers(wid!),
    enabled: !!wid,
  });

  async function doInvite() {
    try {
      const inv = await createInvite(wid!);
      setInvite({ token: inv.token, url: inv.url });
    } catch (e: any) { push(e?.message ?? "Invite failed", "error"); }
  }

  async function changeRole(uid: string, r: string) {
    try {
      await setMemberRole(wid!, uid, r);
      qc.invalidateQueries({ queryKey: ["members", wid] });
      push("Role updated");
    } catch (e: any) { push(e?.message ?? "Update failed", "error"); }
  }

  return (
    <div className={s.scroll}>
      <div className={s.inner}>
        <div className={s.headRow}>
          <div>
            <div className="serif-d" style={{ fontSize: 32 }}>Members &amp; Roles</div>
            <div style={{ color: "var(--ink-3)", marginTop: 8, fontSize: 13.5 }}>
              Owner ⊃ Collaborator ⊃ Observer. Role is legible at a glance — and re-skins the whole workspace.
            </div>
          </div>
          {canManage && <Button variant="primary" onClick={doInvite}>+ Invite</Button>}
        </div>

        {isLoading ? <Spinner /> : (
          <div className={s.list}>
            {(members ?? []).map((m) => (
              <div key={m.user_id} className={s.row}>
                <div className={s.mAvatar} style={{ background: colorFor(m.email) }}>{initialOf(m.email)}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 600 }}>{m.email}</div>
                  <div className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{m.user_id.slice(0, 8)}</div>
                </div>
                {canManage ? (
                  <select className={`mono ${s.roleSel}`} value={m.role} onChange={(e) => changeRole(m.user_id, e.target.value)}>
                    {ROLES.map((r) => <option key={r} value={r}>{ROLE_META[r].label}</option>)}
                  </select>
                ) : (
                  <div className={s.badge}>{ROLE_META[m.role].sigil} {ROLE_META[m.role].label}</div>
                )}
              </div>
            ))}
          </div>
        )}

        {wid && <ProviderPanel wid={wid} isOwner={role === "owner"} />}

        <div className={s.matrixHead} style={{ marginTop: 38 }}>
          <span className="serif-d" style={{ fontSize: 22 }}>Permission Matrix</span>
          <span className={`mono ${s.tag}`}>policy as data</span>
        </div>
        <div className={s.matrix}>
          <div className={`${s.mrow} ${s.mhead}`}>
            <span className="eyebrow">Action</span>
            <span className="eyebrow" style={{ textAlign: "center", color: "var(--oxblood)" }}>♔ Owner</span>
            <span className="eyebrow" style={{ textAlign: "center" }}>⌇ Collab</span>
            <span className="eyebrow" style={{ textAlign: "center" }}>◉ Observer</span>
          </div>
          {PERMISSION_ROWS.map((r, i) => (
            <div key={r.key} className={s.mrow} style={{ background: i % 2 ? "rgba(36,27,18,0.025)" : undefined }}>
              <span className="mono" style={{ fontSize: 13.5, color: "var(--ink-2)" }}>{r.key}</span>
              {ROLES.map((role) => (
                <span key={role} style={{ textAlign: "center", color: can(role, r.action) ? "var(--verde)" : "var(--ink-faint)" }}>
                  {can(role, r.action) ? "✓" : "·"}
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>

      {invite && (
        <Dialog title="Invite link" onClose={() => setInvite(null)}
          footer={<Button variant="primary" onClick={() => { navigator.clipboard?.writeText(invite.token); push("Token copied"); }}>Copy token</Button>}>
          <div style={{ fontSize: 13, color: "var(--ink-2)" }}>Share this token; the recipient joins as a Collaborator.</div>
          <div className="mono" style={{ wordBreak: "break-all", background: "var(--paper-3)", padding: 12, borderRadius: 8, fontSize: 12 }}>{invite.token}</div>
        </Dialog>
      )}
    </div>
  );
}
