import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { resetPassword } from "@/lib/api";
import { Button } from "@/components/common/Button";
import { Field, Input } from "@/components/common/Input";
import { EmptyState } from "@/components/common/Feedback";
import { useToast } from "@/components/common/Toast";
import { Logo } from "@/components/brand/Logo";
import s from "./picker.module.css";

/**
 * The other end of the reset email.
 *
 * The server has always generated `{frontend}/reset-password?token=…` and
 * nothing served that path, so the link landed on the sign-in page and dropped
 * the token — anyone who forgot their password was locked out for good, with
 * a working backend flow they could not reach. Same shape as the invite link.
 *
 * The token is signed against the account's current password hash, so it stops
 * working the moment the reset lands. That means a stale or reused link is
 * indistinguishable from a tampered one, and the copy has to say so plainly
 * rather than implying the account is at fault.
 */
export function ResetPasswordView() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const nav = useNavigate();
  const { push } = useToast();
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit() {
    if (next !== confirm) { push("The two passwords don't match", "error"); return; }
    if (next.length < 6) { push("Password needs at least 6 characters", "error"); return; }
    setBusy(true);
    try {
      await resetPassword(token, next);
      setDone(true);
    } catch (e: any) {
      push(e?.message ?? "That link is no longer valid", "error");
    } finally { setBusy(false); }
  }

  if (!token) {
    return (
      <EmptyState title="This reset link is incomplete">
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
          <span>It's missing its token — email clients sometimes trim long links.</span>
          <Button onClick={() => nav("/auth")}>Back to sign in</Button>
        </div>
      </EmptyState>
    );
  }

  if (done) {
    return (
      <EmptyState title="Password changed">
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
          <span>That link has now been used up. Sign in with the new password.</span>
          <Button variant="primary" onClick={() => nav("/auth")}>Sign in</Button>
        </div>
      </EmptyState>
    );
  }

  return (
    <div className={s.wrap}>
      <div className={`${s.body} folio`} style={{ maxWidth: 460, margin: "0 auto" }}>
        <div className={s.brandRow} style={{ justifyContent: "center", marginBottom: 18 }}>
          <Logo size={40} /><div className={`brand ${s.brand}`}>Helix</div>
        </div>
        <div className="serif-d" style={{ fontSize: 26, textAlign: "center" }}>Choose a new password</div>
        <div style={{ color: "var(--ink-3)", fontSize: 13.5, textAlign: "center", margin: "8px 0 20px" }}>
          This link works once, and only until it's used.
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Field label="New password (min 6 characters)">
            <Input type="password" value={next} autoFocus autoComplete="new-password"
              onChange={(e) => setNext(e.target.value)} />
          </Field>
          <Field label="Repeat new password">
            <Input type="password" value={confirm} autoComplete="new-password"
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }} />
          </Field>
          <Button variant="primary" disabled={busy || !next || !confirm} onClick={submit}>
            {busy ? "Setting it…" : "Set new password"}
          </Button>
          <Button variant="ghost" onClick={() => nav("/auth")}>Back to sign in</Button>
        </div>
      </div>
    </div>
  );
}
