import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createWorkspace, acceptInvite, listWorkspaces, leaveWorkspace } from "@/lib/api";
import type { Workspace } from "@/lib/types";
import { useSession } from "@/store/session";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Input } from "@/components/common/Input";
import { Dialog } from "@/components/common/Dialog";
import { Logo } from "@/components/brand/Logo";
import { Frontispiece } from "@/components/brand/Frontispiece";
import { ThemeToggle } from "@/components/common/ThemeToggle";
import { ROLE_META } from "@/lib/rbac";
import s from "./picker.module.css";

export function WorkspacePicker() {
  const nav = useNavigate();
  const { push } = useToast();
  const { user, workspaces, setWorkspaces, setActiveWorkspace, logout } = useSession();
  const [dialog, setDialog] = useState<null | "create" | "invite">(null);
  const [leaving, setLeaving] = useState<Workspace | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  function enter(id: string) {
    setActiveWorkspace(id);
    nav(`/w/${id}`);
  }

  async function refresh() {
    setWorkspaces(await listWorkspaces());
  }

  async function doCreate() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const ws = await createWorkspace(text.trim());
      await refresh();
      setDialog(null); setText("");
      enter(ws.id);
    } catch (e: any) { push(e?.message ?? "Create failed", "error"); }
    finally { setBusy(false); }
  }

  async function doAccept() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const ws = await acceptInvite(text.trim());
      await refresh();
      setDialog(null); setText("");
      enter(ws.id);
    } catch (e: any) { push(e?.message ?? "Invalid invite", "error"); }
    finally { setBusy(false); }
  }

  async function doLeave() {
    if (!leaving) return;
    setBusy(true);
    try {
      await leaveWorkspace(leaving.id);
      await refresh();
      push(`Left ${leaving.name}`);
      setLeaving(null);
    } catch (e: any) { push(e?.message ?? "Leave failed", "error"); }
    finally { setBusy(false); }
  }

  return (
    <div className={s.wrap}>
      <div className={s.bg} aria-hidden><Frontispiece size={640} animate={false} /></div>
      <div className={s.head}>
        <div className={s.brandRow}><Logo size={40} /><div className={`brand ${s.brand}`}>Helix</div></div>
        <div className={s.who}>
          <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{user?.email}</span>
          <ThemeToggle />
          <Button variant="ghost" onClick={() => nav("/account")}>Account</Button>
          <Button variant="ghost" onClick={() => { logout(); nav("/auth"); }}>Sign out</Button>
        </div>
      </div>

      <div className={`${s.body} folio`}>
        <div className={s.title}>
          <div className="serif-d" style={{ fontSize: 32 }}>Your workspaces</div>
          <div style={{ color: "var(--ink-3)", marginTop: 6 }}>A workspace is a tenant — its conversations, prompts and members are sealed from every other.</div>
          <div className="chapter-rule" aria-hidden>❦</div>
        </div>

        <div className={s.grid}>
          {workspaces.map((w, i) => (
            <div key={w.id} className={s.card} role="button" tabIndex={0}
              style={{ animationDelay: `${Math.min(i, 8) * 55}ms` }}
              onClick={() => enter(w.id)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); enter(w.id); } }}>
              <div className={s.watermark} aria-hidden><Logo size={120} /></div>
              <div className={s.cardMark}>{w.name.charAt(0).toUpperCase()}</div>
              <div className={s.cardName}>{w.name}</div>
              <div className={`mono ${s.cardRole}`}>{ROLE_META[w.role].sigil} {w.role}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className={s.cardGo}>Enter workspace ⟶</span>
                <div style={{ flex: 1 }} />
                {w.owner_id !== user?.id && (
                  <button className={`mono ${s.cardLeave}`} title={`Leave ${w.name}`}
                    onClick={(e) => { e.stopPropagation(); setLeaving(w); }}>
                    leave
                  </button>
                )}
              </div>
            </div>
          ))}
          <div className={s.actions} style={{ animationDelay: `${Math.min(workspaces.length, 8) * 55}ms` }}>
            <Button variant="primary" onClick={() => { setText(""); setDialog("create"); }}>+ New workspace</Button>
            <Button variant="ghost" onClick={() => { setText(""); setDialog("invite"); }}>Join via invite</Button>
          </div>
        </div>

        {workspaces.length === 0 && (
          <div style={{ color: "var(--ink-3)", fontStyle: "italic", marginTop: 24 }}>
            You're not in any workspace yet — create one to begin.
          </div>
        )}
      </div>

      {dialog === "create" && (
        <Dialog title="New workspace" onClose={() => setDialog(null)}
          footer={<>
            <Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button>
            <Button variant="primary" onClick={doCreate} disabled={busy}>Create</Button>
          </>}>
          <Input placeholder="Workspace name (e.g. Cipher Labs)" value={text} autoFocus
            onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && doCreate()} />
        </Dialog>
      )}
      {dialog === "invite" && (
        <Dialog title="Join via invite" onClose={() => setDialog(null)}
          footer={<>
            <Button variant="ghost" onClick={() => setDialog(null)}>Cancel</Button>
            <Button variant="primary" onClick={doAccept} disabled={busy}>Join</Button>
          </>}>
          <Input placeholder="Paste invite token" value={text} autoFocus
            onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && doAccept()} />
        </Dialog>
      )}
      {leaving && (
        <Dialog title={`Leave ${leaving.name}?`} onClose={() => setLeaving(null)}
          footer={<>
            <Button variant="ghost" onClick={() => setLeaving(null)}>Cancel</Button>
            <Button variant="oxblood" onClick={doLeave} disabled={busy}>Leave workspace</Button>
          </>}>
          <div style={{ fontSize: 13.5, color: "var(--ink-2)" }}>
            You'll lose access to its conversations and prompts until someone invites you back.
            Messages you wrote in shared threads stay part of their conversations.
          </div>
        </Dialog>
      )}
    </div>
  );
}
