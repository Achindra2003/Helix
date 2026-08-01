import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { getToken } from "@/lib/auth";
import { me, listWorkspaces, getHealth } from "@/lib/api";
import { useSession } from "@/store/session";
import { Spinner } from "@/components/common/Feedback";
import { Landing } from "@/routes/Landing";
import { AuthPage } from "@/routes/AuthPage";

// The public pair above ships in the entry chunk; everything below is behind a
// login and loads on demand. A stranger evaluating the repo from the landing
// page should not be downloading the workspace shell, the map and the markdown
// renderer before it paints.
const WorkspacePicker = lazy(() => import("@/routes/WorkspacePicker").then((m) => ({ default: m.WorkspacePicker })));
const AccountView = lazy(() => import("@/routes/AccountView").then((m) => ({ default: m.AccountView })));
const WorkspaceLayout = lazy(() => import("@/routes/WorkspaceLayout").then((m) => ({ default: m.WorkspaceLayout })));
const ChatView = lazy(() => import("@/routes/ChatView").then((m) => ({ default: m.ChatView })));
const LibraryView = lazy(() => import("@/routes/LibraryView").then((m) => ({ default: m.LibraryView })));
const DocsView = lazy(() => import("@/routes/DocsView").then((m) => ({ default: m.DocsView })));
const MembersView = lazy(() => import("@/routes/MembersView").then((m) => ({ default: m.MembersView })));
const MapView = lazy(() => import("@/routes/MapView").then((m) => ({ default: m.MapView })));

function ApiHealthBanner() {
  const [down, setDown] = useState(false);
  const loc = useLocation();
  useEffect(() => {
    let alive = true;
    const ping = () => getHealth().then(() => alive && setDown(false)).catch(() => alive && setDown(true));
    ping();
    const t = setInterval(ping, 15_000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  // the public landing is not a place to show a "start uvicorn" dev notice
  if (!down || loc.pathname === "/") return null;
  return (
    <div style={{
      position: "fixed", top: 0, left: 0, right: 0, zIndex: 70, textAlign: "center",
      background: "var(--oxblood)", color: "var(--on-accent)", fontSize: 13, padding: "6px 12px",
      fontFamily: "var(--font-mono)",
    }}>
      ⚠ Helix API unreachable on :8000 — start the backend (uvicorn api.main:app --port 8000)
    </div>
  );
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = useSession((s) => s.user);
  const loc = useLocation();
  if (!user) return <Navigate to="/auth" replace state={{ from: loc.pathname }} />;
  return <>{children}</>;
}

export function App() {
  const { user, setSession, setWorkspaces } = useSession();
  const [booting, setBooting] = useState(true);

  // Rehydrate the session from a stored token on first load.
  useEffect(() => {
    const token = getToken();
    if (!token) { setBooting(false); return; }
    (async () => {
      try {
        const u = await me();
        setSession(u, token);
        const ws = await listWorkspaces();
        setWorkspaces(ws);
      } catch {
        // invalid/expired token — fall through to auth
      } finally {
        setBooting(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (booting) {
    return (
      <div style={{ height: "100%", display: "grid", placeItems: "center", position: "relative", zIndex: 1 }}>
        <Spinner />
      </div>
    );
  }

  return (
    <div style={{ position: "relative", zIndex: 1, height: "100%" }}>
      <ApiHealthBanner />
      <Suspense fallback={
        <div style={{ height: "100%", display: "grid", placeItems: "center" }}><Spinner /></div>
      }>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/auth" element={user ? <Navigate to="/workspaces" replace /> : <AuthPage />} />
          <Route path="/workspaces" element={<RequireAuth><WorkspacePicker /></RequireAuth>} />
          <Route path="/account" element={<RequireAuth><AccountView /></RequireAuth>} />
          <Route path="/w/:wid" element={<RequireAuth><WorkspaceLayout /></RequireAuth>}>
            <Route index element={<ChatView />} />
            <Route path="map" element={<MapView />} />
            <Route path="library" element={<LibraryView />} />
            <Route path="docs" element={<DocsView />} />
            <Route path="members" element={<MembersView />} />
          </Route>
          <Route path="*" element={<Navigate to={user ? "/workspaces" : "/auth"} replace />} />
        </Routes>
      </Suspense>
    </div>
  );
}
