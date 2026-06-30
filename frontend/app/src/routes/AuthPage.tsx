import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, register, listWorkspaces, getHealth } from "@/lib/api";
import { useSession } from "@/store/session";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Field, Input } from "@/components/common/Input";
import { Logo } from "@/components/brand/Logo";
import { Frontispiece } from "@/components/brand/Frontispiece";
import s from "./auth.module.css";

export function AuthPage() {
  const nav = useNavigate();
  const { push } = useToast();
  const { setSession, setWorkspaces } = useSession();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("maren@cipherlabs.io");
  const [password, setPassword] = useState("alchemist");
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<string>("checking…");

  useEffect(() => {
    getHealth()
      .then((h) => setHealth(`api ✓ (${h.provider})`))
      .catch(() => setHealth("api offline — start backend :8000"));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const res = mode === "signin" ? await login(email, password) : await register(email, password);
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
      <div className={s.frontispiece}>
        <Frontispiece size={760} />
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

          <div className={s.tabs} role="tablist">
            <button type="button" role="tab" aria-selected={mode === "signin"}
              className={mode === "signin" ? s.tabOn : s.tab} onClick={() => setMode("signin")}>Sign in</button>
            <button type="button" role="tab" aria-selected={mode === "signup"}
              className={mode === "signup" ? s.tabOn : s.tab} onClick={() => setMode("signup")}>Create account</button>
          </div>

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

          <div className={`mono ${s.health}`}>
            <span>☁ groq</span><span>·</span><span>⌂ ollama</span><span>·</span>
            <span style={{ color: health.startsWith("api ✓") ? "var(--verde)" : "var(--oxblood)" }}>{health}</span>
          </div>
        </form>
      </div>
    </div>
  );
}
