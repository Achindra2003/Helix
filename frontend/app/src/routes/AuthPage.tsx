import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { login, register, listWorkspaces, getHealth, forgotPassword, getPublicConfig } from "@/lib/api";
import { peekParkedInvite } from "@/routes/InviteView";
import { useSession } from "@/store/session";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Field, Input } from "@/components/common/Input";
import { Logo } from "@/components/brand/Logo";
import { OuroborosHelix } from "@/components/brand/OuroborosHelix";
import { ThemeToggle } from "@/components/common/ThemeToggle";
import s from "./auth.module.css";

export function AuthPage() {
  const nav = useNavigate();
  const reduce = useReducedMotion();
  const { push } = useToast();
  const { setSession, setWorkspaces } = useSession();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  // Empty. These fields shipped pre-filled with maren@cipherlabs.io /
  // alchemist — a demo account of ours — so a stranger's first screen in an
  // open-source product was someone else's login, already typed in, inviting
  // them to press Enter on it. Convenient for us for one session; wrong for
  // everyone after that.
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<string>("checking…");
  // An invite-only instance only lets you create an account if you are holding
  // a link. Assume open until the server says otherwise, so the tab doesn't
  // flash away on the common instance; the server refuses either way, so a
  // wrong guess here costs a rejected form, not an unauthorised account.
  const [registrationOpen, setRegistrationOpen] = useState(true);
  // Peeked, not consumed: InviteView clears it only once the invite is
  // actually accepted, which happens after we land back there post-sign-in.
  const invite = peekParkedInvite();
  const canSignUp = registrationOpen || invite !== null;

  useEffect(() => {
    getHealth()
      .then((h) => setHealth(`api ✓ (${h.provider})`))
      .catch(() => setHealth("api offline — start backend :8000"));
    getPublicConfig()
      .then((c) => setRegistrationOpen(c.registration_open))
      .catch(() => { /* unreachable server: the health line already says so */ });
  }, []);

  // If the instance turns out to be closed while "Create account" is selected,
  // fall back rather than leaving a tab that cannot succeed.
  useEffect(() => {
    if (!canSignUp && mode === "signup") setMode("signin");
  }, [canSignUp, mode]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const res = mode === "signin"
        ? await login(email, password)
        : await register(email, password, invite);
      setSession(res.user, res.token);
      const ws = await listWorkspaces();
      setWorkspaces(ws);
      nav("/workspaces");
    } catch (err: any) {
      push(err?.message ?? "Authentication failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={s.wrap}>
      <ThemeToggle floating />
      <div className={s.frontispiece}>
        <OuroborosHelix size={760} />
        <div className={s.epigraph}>"One shared context — many branching minds."</div>
      </div>
      <div className={s.panel}>
        <form className={s.form} onSubmit={submit}>
          <div className={s.brandRow}>
            <Logo size={52} />
            <div>
              <div className={`brand ${s.brandName}`}>Helix</div>
              <div className={s.tagline}>A collaborative workspace for the recursive mind</div>
            </div>
          </div>

          {/* One tab is not a choice — on a closed instance the tablist would
              be a control that cannot do anything, so it goes entirely and the
              note below the button explains why. */}
          {canSignUp && <div className={s.tabs} role="tablist">
            {(["signin", "signup"] as const).map((m) => (
              <button key={m} type="button" role="tab" aria-selected={mode === m}
                className={mode === m ? s.tabOn : s.tab} onClick={() => setMode(m)}>
                {mode === m && (
                  <motion.span layoutId="authTabPill" className={s.tabPill}
                    transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 38 }} />
                )}
                <span className={s.tabLabel}>{m === "signin" ? "Sign in" : "Create account"}</span>
              </button>
            ))}
          </div>}

          <Field label="Email">
            <Input className="mono" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          </Field>
          <Field label="Password">
            <Input className="mono" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signin" ? "current-password" : "new-password"} />
          </Field>

          <Button variant="primary" type="submit" disabled={busy} style={{ padding: 13, fontSize: 15 }}>
            {busy ? "…" : mode === "signin" ? "Enter workspace ⟶" : "Create account ⟶"}
          </Button>

          {/* The reset flow existed on the server and had no way in from here,
              so forgetting your password meant losing the account. */}
          {mode === "signin" && (
            <button type="button" className={s.forgot} disabled={busy}
              onClick={async () => {
                if (!email.trim()) { push("Enter your email first", "error"); return; }
                setBusy(true);
                try {
                  await forgotPassword(email.trim());
                  // Deliberately the same message whether or not that address
                  // has an account — the endpoint refuses to be an enumerator,
                  // and the UI must not answer what the API declined to.
                  push("If that address has an account, a reset link is on its way");
                } catch {
                  push("If that address has an account, a reset link is on its way");
                } finally { setBusy(false); }
              }}>
              Forgot your password?
            </button>
          )}

          {/* Says why there is no way to sign up, rather than leaving a visitor
              to conclude the page is broken. */}
          {!canSignUp && (
            <p className={s.closedNote}>
              This Helix is invite-only. Ask someone on the team for an invite
              link to create an account.
            </p>
          )}

          {/* Only the server's own state. `☁ groq · ⌂ ollama` used to sit here
              too, naming providers to someone who has not signed in and cannot
              choose one — a workspace picks its provider after you are inside.
              What is left is the one thing this screen can't do without: on a
              self-hosted Helix, "the backend isn't running" is the most likely
              reason the form fails, and it is worth saying before it does. */}
          <div className={`mono ${s.health}`}>
            <span style={{ color: health.startsWith("api ✓") ? "var(--verde)" : "var(--oxblood)" }}>{health}</span>
          </div>
        </form>
      </div>
    </div>
  );
}
