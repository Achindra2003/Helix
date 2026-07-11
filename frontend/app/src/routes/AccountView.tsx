import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { changePassword, deleteAccount } from "@/lib/api";
import { useSession } from "@/store/session";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Field, Input } from "@/components/common/Input";
import { Dialog } from "@/components/common/Dialog";
import { Logo } from "@/components/brand/Logo";
import { ThemeToggle } from "@/components/common/ThemeToggle";
import s from "./picker.module.css";

/** Account settings: the page behind the rail avatar. Change password, and the
 * one truly irreversible action — deleting the account (the server refuses
 * while you still own a workspace, so a team's space can't vanish with you). */
export function AccountView() {
  const nav = useNavigate();
  const { push } = useToast();
  const { user, logout } = useSession();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function doChangePassword() {
    if (!current || !next) return;
    if (next !== confirm) { push("New passwords don't match", "error"); return; }
    if (next.length < 6) { push("New password needs at least 6 characters", "error"); return; }
    setBusy(true);
    try {
      await changePassword(current, next);
      setCurrent(""); setNext(""); setConfirm("");
      push("Password changed");
    } catch (e: any) { push(e?.message ?? "Change failed", "error"); }
    finally { setBusy(false); }
  }

  async function doDeleteAccount() {
    setBusy(true);
    try {
      await deleteAccount();
      logout();
      nav("/auth");
    } catch (e: any) {
      // 409 owns_workspaces carries the list of blocking workspaces.
      push(e?.message ?? "Delete failed", "error");
      setConfirmDelete(false);
    } finally { setBusy(false); }
  }

  return (
    <div className={s.wrap}>
      <div className={s.head}>
        <div className={s.brandRow}><Logo size={40} /><div className={`brand ${s.brand}`}>Helix</div></div>
        <div className={s.who}>
          <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{user?.email}</span>
          <ThemeToggle />
          <Button variant="ghost" onClick={() => nav("/workspaces")}>← Workspaces</Button>
        </div>
      </div>

      <div className={`${s.body} folio`} style={{ maxWidth: 640 }}>
        <div className={s.title}>
          <div className="serif-d" style={{ fontSize: 32 }}>Your account</div>
          <div style={{ color: "var(--ink-3)", marginTop: 6 }}>
            Signed in as <span className="mono">{user?.email}</span>
          </div>
          <div className="chapter-rule" aria-hidden>❦</div>
        </div>

        <div className="serif-d" style={{ fontSize: 22, marginBottom: 14 }}>Change password</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 420 }}>
          <Field label="Current password">
            <Input type="password" value={current} autoComplete="current-password"
              onChange={(e) => setCurrent(e.target.value)} />
          </Field>
          <Field label="New password (min 6 characters)">
            <Input type="password" value={next} autoComplete="new-password"
              onChange={(e) => setNext(e.target.value)} />
          </Field>
          <Field label="Repeat new password">
            <Input type="password" value={confirm} autoComplete="new-password"
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && doChangePassword()} />
          </Field>
          <div>
            <Button variant="primary" disabled={busy || !current || !next} onClick={doChangePassword}>
              Change password
            </Button>
          </div>
        </div>

        <div className="serif-d" style={{ fontSize: 22, margin: "38px 0 8px", color: "var(--oxblood)" }}>
          Danger zone
        </div>
        <div style={{ fontSize: 13.5, color: "var(--ink-2)", marginBottom: 14, maxWidth: 480 }}>
          Deleting your account removes you from every workspace and signs you out for good.
          If you still <b>own</b> a workspace, the server will refuse — delete the workspace
          (TEAM page) or have ownership moved first, so a team's shared space can never
          disappear with one account.
        </div>
        <Button variant="oxblood" disabled={busy} onClick={() => setConfirmDelete(true)}>
          Delete my account
        </Button>
      </div>

      {confirmDelete && (
        <Dialog title="Delete this account?" onClose={() => setConfirmDelete(false)}
          footer={<>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button variant="oxblood" disabled={busy} onClick={doDeleteAccount}>Delete forever</Button>
          </>}>
          <div style={{ fontSize: 13.5, color: "var(--ink-2)" }}>
            This can't be undone. Your memberships are removed; messages you wrote in shared
            threads remain part of their conversations (attributed to a departed teammate).
          </div>
        </Dialog>
      )}
    </div>
  );
}
