import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { api, type Health } from "../lib/api";
import { Logo } from "./ui/Logo";
import { Avatar } from "./ui/Avatar";
import { Button } from "./ui/Button";

function HealthDot() {
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);
  useEffect(() => {
    api.health().then(setHealth).catch(() => setDown(true));
  }, []);

  const color = down ? "bg-danger" : health ? "bg-success" : "bg-muted";
  const label = down
    ? "backend offline"
    : health
      ? `online · ${health.provider}`
      : "checking…";

  return (
    <span className="hidden items-center gap-2 text-xs text-muted sm:flex">
      <span className={`size-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}

export function Topbar({ children }: { children?: React.ReactNode }) {
  const { user, logout } = useAuth();
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface/60 px-4 backdrop-blur">
      <div className="flex items-center gap-4">
        <Link to="/">
          <Logo />
        </Link>
        {children}
      </div>
      <div className="flex items-center gap-4">
        <HealthDot />
        {user && (
          <div className="flex items-center gap-3">
            <Avatar email={user.email} />
            <Button variant="ghost" size="sm" onClick={logout}>
              Sign out
            </Button>
          </div>
        )}
      </div>
    </header>
  );
}
