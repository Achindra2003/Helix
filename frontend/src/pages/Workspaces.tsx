import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type Workspace } from "../lib/api";
import { Topbar } from "../components/Topbar";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { HelixMark } from "../components/ui/Logo";
import { Spinner } from "../components/ui/Spinner";

const roleStyle: Record<string, string> = {
  owner: "text-violet border-violet/40 bg-violet/10",
  collaborator: "text-cyan border-cyan/40 bg-cyan/10",
  observer: "text-muted border-line bg-surface-2",
};

function RoleBadge({ role }: { role: string }) {
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs capitalize ${roleStyle[role] ?? roleStyle.observer}`}
    >
      {role}
    </span>
  );
}

export function Workspaces() {
  const navigate = useNavigate();
  const [items, setItems] = useState<Workspace[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setItems(await api.listWorkspaces());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load.");
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const ws = await api.createWorkspace(name.trim());
      navigate(`/w/${ws.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create.");
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <Topbar />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Workspaces</h1>
            <p className="mt-1 text-sm text-muted">
              Shared, branchable AI workspaces for your team.
            </p>
          </div>
          {!creating && (
            <Button onClick={() => setCreating(true)}>+ New workspace</Button>
          )}
        </div>

        {creating && (
          <form
            onSubmit={onCreate}
            className="mb-6 flex items-end gap-3 rounded-xl border border-line bg-surface p-4"
          >
            <div className="flex-1">
              <Input
                label="Workspace name"
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="rag-quality"
              />
            </div>
            <Button type="submit" loading={busy}>
              Create
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setCreating(false)}
            >
              Cancel
            </Button>
          </form>
        )}

        {error && <p className="mb-4 text-sm text-danger">{error}</p>}

        {items === null ? (
          <div className="grid place-items-center py-20">
            <Spinner size={26} />
          </div>
        ) : items.length === 0 ? (
          <div className="grid place-items-center rounded-xl border border-dashed border-line py-20 text-center app-glow">
            <HelixMark size={40} />
            <p className="mt-4 font-medium">No workspaces yet</p>
            <p className="mt-1 text-sm text-muted">
              Create your first workspace to start collaborating.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((ws) => (
              <button
                key={ws.id}
                onClick={() => navigate(`/w/${ws.id}`)}
                className="group flex flex-col rounded-xl border border-line bg-surface p-5 text-left transition hover:border-violet/50 hover:bg-surface-2"
              >
                <div className="mb-3 flex items-center justify-between">
                  <HelixMark size={24} />
                  <RoleBadge role={ws.role} />
                </div>
                <span className="font-medium tracking-tight group-hover:text-helix">
                  {ws.name}
                </span>
                <span className="mt-1 text-xs text-muted">
                  Created {new Date(ws.created_at).toLocaleDateString()}
                </span>
              </button>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
