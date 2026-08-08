import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listMembers, createInvite, setMemberRole, removeMember,
  listInvites, revokeInvite,
} from "@/lib/api";
import { can, PERMISSION_ROWS, ROLE_META } from "@/lib/rbac";
import { useEffectiveRole, useActiveWorkspace } from "@/store/session";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Dialog } from "@/components/common/Dialog";
import { Spinner } from "@/components/common/Feedback";
import { initialOf, colorFor } from "@/lib/format";
import { ROLE_SIGIL } from "@/lib/glyphs";
import type { Member, Role } from "@/lib/types";
import s from "./members.module.css";

const ROLES: Role[] = ["owner", "collaborator", "observer"];

export function MembersView() {
  const { wid } = useParams();
  const qc = useQueryClient();
  const { push } = useToast();
  const role = useEffectiveRole();
  const ws = useActiveWorkspace();
  const canManage = can(role, "member.manage");
  const [invite, setInvite] = useState<{ token: string; url: string; role: Role } | null>(null);
  // Observers exist to be invited — a stakeholder who should read the record
  // without being able to spend the workspace's key. Without this the role was
  // reachable only by inviting someone and then demoting them.
  const [inviteRole, setInviteRole] = useState<Role>("collaborator");
  const [confirmKick, setConfirmKick] = useState<Member | null>(null);

  // Outstanding invites — owner-only endpoint, so only fetch as one.
  const { data: inviteData } = useQuery({
    queryKey: ["invites", wid],
    queryFn: () => listInvites(wid!),
    enabled: !!wid && canManage,
  });
  const invites = inviteData?.items ?? [];

  const { data: members, isLoading } = useQuery({
    queryKey: ["members", wid],
    queryFn: () => listMembers(wid!),
    enabled: !!wid,
  });

  // Clipboard writes are refused in some contexts (no permission, insecure
  // origin). Say so instead of throwing into the void — the link is on screen
  // either way.
  function copyLink(url: string) {
    Promise.resolve(navigator.clipboard?.writeText(url))
      .then(() => push("Invite link copied"))
      .catch(() => push("Couldn't copy — select the link above instead", "error"));
  }

  async function doInvite() {
    try {
      const inv = await createInvite(wid!, inviteRole);
      setInvite({ token: inv.token, url: inv.url, role: inviteRole });
      qc.invalidateQueries({ queryKey: ["invites", wid] });
    } catch (e: any) { push(e?.message ?? "Invite failed", "error"); }
  }

  async function doRevoke(token: string) {
    try {
      await revokeInvite(wid!, token);
      qc.invalidateQueries({ queryKey: ["invites", wid] });
      push("Invite revoked — the link no longer admits anyone");
    } catch (e: any) { push(e?.message ?? "Revoke failed", "error"); }
  }

  async function doKick() {
    if (!confirmKick) return;
    try {
      await removeMember(wid!, confirmKick.user_id);
      qc.invalidateQueries({ queryKey: ["members", wid] });
      push(`${confirmKick.email} removed from the workspace`);
      setConfirmKick(null);
    } catch (e: any) { push(e?.message ?? "Remove failed", "error"); }
  }

  async function changeRole(uid: string, r: string) {
    try {
      await setMemberRole(wid!, uid, r);
      qc.invalidateQueries({ queryKey: ["members", wid] });
      push("Role updated");
    } catch (e: any) { push(e?.message ?? "Update failed", "error"); }
  }

  return (
    <div className={`${s.scroll} folio`}>
      <div className={s.inner}>
        <div className={s.headRow}>
          <div>
            <div className="serif-d" style={{ fontSize: 32 }}>Members &amp; Roles</div>
            <div style={{ color: "var(--ink-3)", marginTop: 8, fontSize: 13 }}>
              Owner ⊃ Collaborator ⊃ Observer. Role is legible at a glance — and re-skins the whole workspace.
            </div>
          </div>
          {canManage && (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <select className={`mono ${s.roleSel}`} value={inviteRole}
                title="What the invited person will be able to do"
                onChange={(e) => setInviteRole(e.target.value as Role)}>
                <option value="collaborator">as Collaborator</option>
                <option value="observer">as Observer</option>
              </select>
              <Button variant="primary" onClick={doInvite}>+ Invite</Button>
            </div>
          )}
        </div>
        <div className="chapter-rule" aria-hidden>❦</div>

        {isLoading ? <Spinner /> : (
          <div className={s.list}>
            {(members ?? []).map((m) => (
              <div key={m.user_id} className={s.row}>
                <div className={s.mAvatar} style={{ background: colorFor(m.email) }}>{initialOf(m.email)}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 15, fontWeight: 600 }}>{m.email}</div>
                  <div className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{m.user_id.slice(0, 8)}</div>
                </div>
                {/* The canonical owner gets a badge, not a dropdown: the server
                    refuses every change to them ("Cannot demote the workspace
                    owner"), so offering the choice only produces an error. */}
                {canManage && m.user_id !== ws?.owner_id ? (
                  <select className={`mono ${s.roleSel}`} value={m.role} onChange={(e) => changeRole(m.user_id, e.target.value)}>
                    {ROLES.map((r) => <option key={r} value={r}>{ROLE_META[r].label}</option>)}
                  </select>
                ) : (
                  <div className={s.badge}>{ROLE_META[m.role].sigil} {ROLE_META[m.role].label}</div>
                )}
                {canManage && m.user_id !== ws?.owner_id && (
                  <Button variant="ghost" style={{ fontSize: 12, color: "var(--oxblood)" }}
                    title={`Remove ${m.email} from the workspace`}
                    onClick={() => setConfirmKick(m)}>
                    remove
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}

        {canManage && invites.length > 0 && (
          <>
            <div className={s.matrixHead} style={{ marginTop: 38 }}>
              <span className="serif-d" style={{ fontSize: 22 }}>Outstanding invites</span>
              <span className={`mono ${s.tag}`}>revocable</span>
            </div>
            <div className={s.list}>
              {invites.map((inv) => (
                <div key={inv.token} className={s.row}>
                  <span style={{ fontSize: 15 }}>✉</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="mono" style={{ fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {inv.token}
                    </div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>
                      joins as {inv.role} · expires {new Date(inv.expires_at).toLocaleDateString()}
                    </div>
                  </div>
                  <Button variant="ghost" style={{ fontSize: 12 }}
                    title="Copy the join link"
                    onClick={() => { copyLink(inv.url); }}>copy link</Button>
                  <Button variant="ghost" style={{ fontSize: 12, color: "var(--oxblood)" }}
                    title="Revoke — the link stops admitting anyone, immediately"
                    onClick={() => doRevoke(inv.token)}>revoke</Button>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Provider, agent tools and the workspace itself used to sit here.
            They describe how the workspace is configured, not who is in it —
            see routes/SettingsView.tsx. */}

        <div className={s.matrixHead} style={{ marginTop: 38 }}>
          <span className="serif-d" style={{ fontSize: 22 }}>Permission Matrix</span>
          <span className={`mono ${s.tag}`}>policy as data</span>
        </div>
        <div className={s.matrix}>
          <div className={`${s.mrow} ${s.mhead}`}>
            <span className="eyebrow">Action</span>
            <span className="eyebrow" style={{ textAlign: "center", color: "var(--oxblood)" }}>{ROLE_SIGIL.owner} Owner</span>
            <span className="eyebrow" style={{ textAlign: "center" }}>{ROLE_SIGIL.collaborator} Collab</span>
            <span className="eyebrow" style={{ textAlign: "center" }}>{ROLE_SIGIL.observer} Observer</span>
          </div>
          {PERMISSION_ROWS.map((r, i) => (
            <div key={r.key} className={s.mrow} style={{ background: i % 2 ? "var(--stripe)" : undefined }}>
              <span className="mono" style={{ fontSize: 13, color: "var(--ink-2)" }}>{r.key}</span>
              {ROLES.map((role) => (
                <span key={role} style={{ textAlign: "center", color: can(role, r.action) ? "var(--verde)" : "var(--ink-3)" }}>
                  {can(role, r.action) ? "✓" : "·"}
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>

      {confirmKick && (
        <Dialog title={`Remove ${confirmKick.email}?`} onClose={() => setConfirmKick(null)}
          footer={<>
            <Button variant="ghost" onClick={() => setConfirmKick(null)}>Cancel</Button>
            <Button variant="oxblood" onClick={doKick}>Remove member</Button>
          </>}>
          <div style={{ fontSize: 13, color: "var(--ink-2)" }}>
            They lose access immediately. Messages they wrote in shared threads stay part of
            those conversations, and they can be invited back at any time.
          </div>
        </Dialog>
      )}
      {invite && (
        <Dialog title="Invite link" onClose={() => setInvite(null)}
          footer={<Button variant="primary"
            onClick={() => copyLink(invite.url)}>
            Copy link
          </Button>}>
          {/* The link, not the token. This dialog used to show the raw token
              and say "share this token", so the join URL the server has always
              generated was never handed to anyone — which is how it stayed
              broken without being noticed. */}
          <div style={{ fontSize: 13, color: "var(--ink-2)" }}>
            Send this link. Whoever opens it joins as {ROLE_META[invite.role].label.toLowerCase()};
            it works once, and you can revoke it below at any time.
          </div>
          <div className="mono" style={{ wordBreak: "break-all", background: "var(--paper-3)", padding: 12, borderRadius: 8, fontSize: 12 }}>{invite.url}</div>
        </Dialog>
      )}
    </div>
  );
}
