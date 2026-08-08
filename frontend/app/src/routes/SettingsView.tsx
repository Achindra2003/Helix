import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { renameWorkspace, deleteWorkspace, listWorkspaces } from "@/lib/api";
import { can } from "@/lib/rbac";
import { useEffectiveRole, useActiveWorkspace, useSession } from "@/store/session";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Dialog } from "@/components/common/Dialog";
import { Input } from "@/components/common/Input";
import { ProviderPanel } from "./ProviderPanel";
import { ToolsPanel } from "./ToolsPanel";
import { McpPanel } from "./McpPanel";
import s from "./members.module.css";

/**
 * Everything about how this workspace is *configured*.
 *
 * These three panels used to live at the bottom of the TEAM page, under a
 * heading that said "Members & Roles". Which model answers your questions,
 * whose key pays for it, what the agent is allowed to touch, and what the
 * workspace is called are not facts about your teammates — and stacking them
 * under a page about people is most of why that screen read as a mess.
 *
 * The split is by question, not by permission: TEAM answers "who is here and
 * what may they do", this answers "how is this workspace set up".
 */
export function SettingsView() {
  const { wid } = useParams();
  const nav = useNavigate();
  const { push } = useToast();
  const role = useEffectiveRole();
  const ws = useActiveWorkspace();
  const setWorkspaces = useSession((st) => st.setWorkspaces);
  const canManageWs = can(role, "workspace.manage");
  const [wsName, setWsName] = useState("");
  const [wsBusy, setWsBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => { setWsName(ws?.name ?? ""); }, [ws?.name]);

  async function doRename() {
    if (!wid || !wsName.trim()) return;
    setWsBusy(true);
    try {
      await renameWorkspace(wid, wsName.trim());
      // The name lives in the session's workspace list (TopBar, picker) —
      // refresh it so the whole shell updates, not just this page.
      setWorkspaces(await listWorkspaces());
      push("Workspace renamed");
    } catch (e: any) {
      push(e?.message ?? "Rename failed", "error");
    } finally { setWsBusy(false); }
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
            <div className="serif-d" style={{ fontSize: 32 }}>Workspace settings</div>
            <div style={{ color: "var(--ink-3)", marginTop: 8, fontSize: 13 }}>
              Which model this workspace thinks with, what its agent may reach for,
              and the workspace itself.
            </div>
          </div>
        </div>
        <div className="chapter-rule" aria-hidden>❦</div>

        {wid && <ProviderPanel wid={wid} isOwner={role === "owner"} />}
        {wid && <ToolsPanel wid={wid} isOwner={role === "owner"} />}
        {wid && <McpPanel wid={wid} isOwner={role === "owner"} />}

        {canManageWs && (
          <>
            <div className={s.matrixHead} style={{ marginTop: 38 }}>
              <span className="serif-d" style={{ fontSize: 22 }}>This workspace</span>
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
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>
                Deleting removes every conversation, branch, document, run record and invite in
                this workspace, for every member — there is no undo.
              </div>
            </div>
          </>
        )}
      </div>

      {confirmDelete && (
        <Dialog title={`Delete ${ws?.name ?? "this workspace"}?`} onClose={() => setConfirmDelete(false)}
          footer={<>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button variant="oxblood" disabled={wsBusy} onClick={doDeleteWorkspace}>Delete forever</Button>
          </>}>
          <div style={{ fontSize: 13, color: "var(--ink-2)" }}>
            Every conversation, branch, document, run record and invite in this workspace is
            deleted — for every member. This cannot be undone.
          </div>
        </Dialog>
      )}
    </div>
  );
}
