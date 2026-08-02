import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { acceptInvite, previewInvite } from "@/lib/api";
import { useSession } from "@/store/session";
import { Spinner, EmptyState } from "@/components/common/Feedback";
import { Button } from "@/components/common/Button";

/**
 * Landing page for an invite link.
 *
 * The server has always handed out `{frontend}/invite/{token}`, but nothing
 * ever served that path — the catch-all redirected to the workspace picker and
 * the invite silently evaporated. The only way in was to know that you should
 * paste the raw token into a dialog, which is not something a person receiving
 * a link would guess.
 *
 * Signed out, the token is parked and the visitor is sent to sign in first,
 * because accepting an invite has to attach to an account.
 */
const PARKED = "helix.pendingInvite";

export function InviteView() {
  const { token } = useParams();
  const nav = useNavigate();
  const user = useSession((st) => st.user);
  const [workspace, setWorkspace] = useState<string | null>(null);
  const [error, setError] = useState("");
  const accepting = useRef(false);

  useEffect(() => {
    if (!token) return;
    if (!user) {
      // Park it and come back after sign-in.
      try { sessionStorage.setItem(PARKED, token); } catch { /* private mode */ }
      nav("/auth", { replace: true });
      return;
    }
    // StrictMode double-invokes effects in dev; accepting twice would show a
    // spurious "already used" error on a perfectly good invite.
    if (accepting.current) return;
    accepting.current = true;

    (async () => {
      try {
        const preview = await previewInvite(token).catch(() => null);
        if (preview) setWorkspace(preview.workspace_name);
        const ws = await acceptInvite(token);
        try { sessionStorage.removeItem(PARKED); } catch { /* ignore */ }
        nav(`/w/${ws.id}`, { replace: true });
      } catch (e: any) {
        setError(e?.message ?? "This invite is no longer valid.");
      }
    })();
  }, [token, user, nav]);

  if (error) {
    return (
      <EmptyState title="This invite didn't work">
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
          <span>{error}</span>
          <span style={{ fontSize: 13, color: "var(--ink-3)" }}>
            Invites expire, and each one can only be used once. Ask whoever sent
            it for a fresh link.
          </span>
          <Button onClick={() => nav("/workspaces")}>Go to your workspaces</Button>
        </div>
      </EmptyState>
    );
  }

  return (
    <div style={{ height: "100%", display: "grid", placeItems: "center" }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
        <Spinner />
        <span style={{ fontSize: 14, color: "var(--ink-3)" }}>
          {workspace ? `Joining ${workspace}…` : "Checking your invite…"}
        </span>
      </div>
    </div>
  );
}

/** The token parked by an invite link followed while signed out.
 *
 * Peek, not take: this is read during render to decide where sign-in should
 * land, and the token is only cleared once the invite is actually accepted. */
export function peekParkedInvite(): string | null {
  try {
    return sessionStorage.getItem(PARKED);
  } catch {
    return null;
  }
}
