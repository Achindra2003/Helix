import { useEffect, useState } from "react";
import { Outlet, useLocation, useParams } from "react-router-dom";
import { Rail } from "@/components/shell/Rail";
import { TopBar } from "@/components/shell/TopBar";
import { SearchOverlay } from "@/components/shell/SearchOverlay";
import { connectRoom, disconnectRoom, onRoomEvent } from "@/lib/realtime";
import { useSession, useEffectiveRole } from "@/store/session";
import { useNotifications } from "@/store/notifications";
import { useUnread } from "@/store/unread";
import { usePresenceStore } from "@/store/presence";
import s from "@/components/shell/shell.module.css";

export function WorkspaceLayout() {
  const { wid } = useParams();
  const loc = useLocation();
  const role = useEffectiveRole();
  const { activeWorkspaceId, setActiveWorkspace } = useSession();
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    if (wid && wid !== activeWorkspaceId) setActiveWorkspace(wid);
  }, [wid, activeWorkspaceId, setActiveWorkspace]);

  // Join the workspace's realtime room (presence + live fan-out) while inside it.
  useEffect(() => {
    if (!wid) return;
    connectRoom(wid);
    return () => disconnectRoom();
  }, [wid]);

  // Notification center + unread markers: one shell-level listener over the
  // room's events, so activity you'd otherwise miss (a teammate's deep run
  // finishing, a turn landing in a thread you're not reading) is visible.
  // Both stores are session-scoped by design.
  useEffect(() => {
    if (!wid) return;
    useUnread.getState().reset(); // markers belong to one workspace at a time
    const off = onRoomEvent((ev) => {
      if (ev.kind === "conversation.created") {
        useUnread.getState().mark(ev.conversation_id);
        return;
      }
      if (ev.kind !== "run_event") return;
      const e = ev.event;
      // A teammate's turn began in some thread — dot it; ChatView clears the
      // marker for whichever thread is actually on screen.
      if (e?.kind === "user_node") {
        useUnread.getState().mark(ev.conversation_id);
      }
      if (e?.kind !== "complete") return;
      // The relay excludes the sender, so this is always a teammate's run.
      const who =
        usePresenceStore.getState().users.find((u) => u.user_id === ev.author_id)?.email
        ?? "a teammate";
      const outcome = e.status === "killed" ? "was stopped" : e.status === "error" ? "errored" : "finished";
      useNotifications.getState().add({
        text: `${who}'s deep run ${outcome} (${e.stop_reason ?? ""})`.trim(),
        conversationId: ev.conversation_id,
      });
    });
    return off;
  }, [wid]);

  // Ctrl/Cmd+K: the workspace-wide search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const tail = loc.pathname.split("/").slice(3).join("/"); // after /w/:wid
  const active = tail.startsWith("library") ? "library" : tail.startsWith("docs") ? "docs" : tail.startsWith("members") ? "members" : tail.startsWith("map") ? "map" : "";
  const viewLabel = active === "library" ? "prompt library" : active === "docs" ? "knowledge base" : active === "members" ? "members & roles" : active === "map" ? "the map" : "conversations";

  return (
    <div className={s.shell}>
      <Rail active={active} onSearch={() => setSearchOpen(true)} />
      <div className={`${s.main} ${role === "observer" ? s.dim : ""}`}>
        <TopBar viewLabel={viewLabel} />
        <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
          <Outlet />
        </div>
      </div>
      {searchOpen && wid && <SearchOverlay wid={wid} onClose={() => setSearchOpen(false)} />}
    </div>
  );
}
