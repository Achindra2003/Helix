import { useEffect } from "react";
import { Outlet, useLocation, useParams } from "react-router-dom";
import { Rail } from "@/components/shell/Rail";
import { TopBar } from "@/components/shell/TopBar";
import { connectRoom, disconnectRoom } from "@/lib/realtime";
import { useSession, useEffectiveRole } from "@/store/session";
import s from "@/components/shell/shell.module.css";

export function WorkspaceLayout() {
  const { wid } = useParams();
  const loc = useLocation();
  const role = useEffectiveRole();
  const { activeWorkspaceId, setActiveWorkspace } = useSession();

  useEffect(() => {
    if (wid && wid !== activeWorkspaceId) setActiveWorkspace(wid);
  }, [wid, activeWorkspaceId, setActiveWorkspace]);

  // Join the workspace's realtime room (presence + live fan-out) while inside it.
  useEffect(() => {
    if (!wid) return;
    connectRoom(wid);
    return () => disconnectRoom();
  }, [wid]);

  const tail = loc.pathname.split("/").slice(3).join("/"); // after /w/:wid
  const active = tail.startsWith("library") ? "library" : tail.startsWith("members") ? "members" : tail.startsWith("map") ? "map" : "";
  const viewLabel = active === "library" ? "prompt library" : active === "members" ? "members & roles" : active === "map" ? "the map" : "conversations";

  return (
    <div className={s.shell}>
      <Rail active={active} />
      <div className={`${s.main} ${role === "observer" ? s.dim : ""}`}>
        <TopBar viewLabel={viewLabel} />
        <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
