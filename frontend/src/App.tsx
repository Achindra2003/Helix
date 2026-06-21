import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { FullPageSpinner } from "./components/ui/Spinner";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { Workspaces } from "./pages/Workspaces";
import { WorkspacePage } from "./pages/Workspace";
import { InviteAccept } from "./pages/InviteAccept";

function ProtectedRoute() {
  const { user, loading } = useAuth();
  if (loading) return <FullPageSpinner />;
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/invite/:token" element={<InviteAccept />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<Workspaces />} />
        <Route path="/w/:id" element={<WorkspacePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
