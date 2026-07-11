import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listMembers, createInvite, setMemberRole, removeMember,
  listInvites, revokeInvite,
  renameWorkspace, deleteWorkspace, listWorkspaces,
} from "@/lib/api";
import { can, PERMISSION_ROWS, ROLE_META } from "@/lib/rbac";
import { useEffectiveRole, useActiveWorkspace, useSession } from "@/store/session";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Dialog } from "@/components/common/Dialog";
import { Input } from "@/components/common/Input";
import { Spinner } from "@/components/common/Feedback";
import { initialOf, colorFor } from "@/lib/format";
import type { Member, Role } from "@/lib/types";
import { ProviderPanel } from "./ProviderPanel";
import s from "./members.module.css";

const ROLES: Role[] = ["owner", "collaborator", "observer"];

export function MembersView() {
  const { wid } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { push } = useToast();
  const role = useEffectiveRole();
  const ws = useActiveWorkspace();
  const setWorkspaces = useSession((st) => st.setWorkspaces);
  const canManage = can(role, "member.manage");
  const canManageWs = can(role, "workspace.manage");
  const [invite, setInvite] = useState<{ token: string; url: string } | null>(null);
  const [wsName, setWsName] = useState("");
  const [wsBusy, setWsBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmKick, setConfirmKick] = useState<Member | null>(null);
  useEffect(() => { setWsName(ws?.name ?? ""); }, [ws?.name]);

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

  async function doInvite() {
    try {
      const inv = await createInvite(wid!);
      setInvite({ token: inv.token, url: inv.url });
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

  async function doRename() {
    const name = wsName.trim();
    if (!wid || !name || name === ws?.name) return;
    setWsBusy(true);
    try {
      await renameWorkspace(wid, name);
      // The name lives in the session's workspace list (TopBar, picker) —
      // refresh it so the whole shell updates, not just this page.
      setWorkspaces(await listWorkspaces());
      push("Workspace renamed");
    } catch (e: any) { push(e?.message ?? "Rename failed", "error"); }
    finally { setWsBusy(false); }
  }

  async function doDeleteWorkspace() {
    if (!wid) return;
    setWsBusy(true);
    try {
      await deleteWorkspace(wid);
      setWorkspaces(await listWorkspaces());
      nav("/workspaces");
      push("Workspace deleted");
    } catch (e: any) {
      push(e?.message ?? "Delete failed", "error");
      setConfirmDelete(false);
    } finally { setWsBusy(false); }
  }

  return (
    <div className={`${s.scroll} folio`}>
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
                {canManage ? (
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
                    <div className="mono" style={{ fontSize: 12.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {inv.token}
                    </div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>
                      joins as {inv.role} · expires {new Date(inv.expires_at).toLocaleDateString()}
                    </div>
                  </div>
                  <Button variant="ghost" style={{ fontSize: 12 }}
                    onClick={() => { navigator.clipboard?.writeText(inv.token); push("Token copied"); }}>copy</Button>
                  <Button variant="ghost" style={{ fontSize: 12, color: "var(--oxblood)" }}
                    title="Revoke — the link stops admitting anyone, immediately"
                    onClick={() => doRevoke(inv.token)}>revoke</Button>
                </div>
              ))}
            </div>
          </>
        )}

        {wid && <ProviderPanel wid={wid} isOwner={role === "owner"} />}

        {canManageWs && (
          <>
            <div className={s.matrixHead} style={{ marginTop: 38 }}>
              <span className="serif-d" style={{ fontSize: 22 }}>Workspace</span>
              <span className={`mono ${s.tag}`}>owner only</span>
            </div>
            <div className={s.row} style={{ flexDirection: "column", alignItems: "stretch", gap: 14 }}>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <Input value={wsName} onChange={(e) => setWsName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && doRename()}
                  style={{ maxWidth: 320 }} placeholder="Workspace name" />
                <Button variant="primary" disabled={wsBusy || !wsName.trim() || wsName.trim() === ws?.name}
                  onClick={doRename}>Rename</Button>
                <div style={{ flex: 1 }} />
                <Button variant="oxblood" disabled={wsBusy} onClick={() => setConfirmDelete(true)}>
                  Delete workspace
                </Button>
              </div>
              <div style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
                Deleting removes every conversation, branch, document, run record and invite in
                this workspace, for every member — there is no undo.
              </div>
            </div>
          </>
        )}

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
            <div key={r.key} className={s.mrow} style={{ background: i % 2 ? "var(--stripe)" : undefined }}>
              <span className="mono" style={{ fontSize: 13.5, color: "var(--ink-2)" }}>{r.key}</span>
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
          <div style={{ fontSize: 13.5, color: "var(--ink-2)" }}>
            They lose access immediately. Messages they wrote in shared threads stay part of
            those conversations, and they can be invited back at any time.
          </div>
        </Dialog>
      )}
      {confirmDelete && (
        <Dialog title={`Delete ${ws?.name ?? "this workspace"}?`} onClose={() => setConfirmDelete(false)}
          footer={<>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button variant="oxblood" disabled={wsBusy} onClick={doDeleteWorkspace}>Delete forever</Button>
          </>}>
          <div style={{ fontSize: 13.5, color: "var(--ink-2)" }}>
            Every conversation, branch, document, run record and invite in this workspace is
            deleted — for every member. This cannot be undone.
          </div>
        </Dialog>
      )}
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
