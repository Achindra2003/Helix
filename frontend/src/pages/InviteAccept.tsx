import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { AuthLayout } from "./AuthLayout";
import { Button } from "../components/ui/Button";
import { Spinner } from "../components/ui/Spinner";

export function InviteAccept() {
  const { token } = useParams<{ token: string }>();
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [wsName, setWsName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    api
      .previewInvite(token)
      .then((p) => setWsName(p.workspace_name))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Invalid invite.")
      );
  }, [token]);

  async function onAccept() {
    if (!token) return;
    setBusy(true);
    try {
      const ws = await api.acceptInvite(token);
      navigate(`/w/${ws.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not join.");
      setBusy(false);
    }
  }

  const subtitle = error
    ? "This invite can't be used"
    : wsName
      ? `You've been invited to join ${wsName}`
      : "Checking your invite…";

  return (
    <AuthLayout
      title="Join a workspace"
      subtitle={subtitle}
      footer={
        <Link to="/" className="text-helix font-medium">
          Go to your workspaces
        </Link>
      }
    >
      {error ? (
        <p className="text-center text-sm text-danger">{error}</p>
      ) : !wsName ? (
        <div className="grid place-items-center py-4">
          <Spinner />
        </div>
      ) : loading ? (
        <div className="grid place-items-center py-4">
          <Spinner />
        </div>
      ) : user ? (
        <Button className="w-full" loading={busy} onClick={onAccept}>
          Join {wsName}
        </Button>
      ) : (
        <div className="space-y-3 text-center">
          <p className="text-sm text-muted">Sign in to accept this invite.</p>
          <Link to="/login">
            <Button className="w-full">Sign in to continue</Button>
          </Link>
        </div>
      )}
    </AuthLayout>
  );
}
