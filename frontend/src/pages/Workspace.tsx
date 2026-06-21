import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  api,
  ApiError,
  streamChat,
  type Member,
  type Workspace,
} from "../lib/api";
import { Topbar } from "../components/Topbar";
import { Button } from "../components/ui/Button";
import { Avatar } from "../components/ui/Avatar";
import { FullPageSpinner } from "../components/ui/Spinner";

interface ChatMsg {
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
}

function Sidebar({
  ws,
  members,
  onInvite,
  inviteUrl,
}: {
  ws: Workspace;
  members: Member[];
  onInvite: () => void;
  inviteUrl: string | null;
}) {
  const navItems = [
    { label: "Conversations", hint: "M2", active: true },
    { label: "Prompt library", hint: "M5" },
    { label: "Branch tree", hint: "M4" },
    { label: "Deep Reasoning", hint: "M6" },
  ];
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-line bg-surface/40">
      <div className="border-b border-line p-4">
        <p className="text-xs uppercase tracking-wide text-muted">Workspace</p>
        <p className="mt-0.5 truncate font-medium tracking-tight">{ws.name}</p>
      </div>

      <nav className="flex flex-col gap-1 p-3">
        {navItems.map((it) => (
          <button
            key={it.label}
            disabled={!it.active}
            className={
              "flex items-center justify-between rounded-lg px-3 py-2 text-sm transition " +
              (it.active
                ? "bg-surface-2 text-fg"
                : "text-muted/70 hover:text-muted cursor-default")
            }
          >
            <span>{it.label}</span>
            <span className="rounded border border-line px-1.5 py-0.5 text-[10px] text-muted">
              {it.hint}
            </span>
          </button>
        ))}
      </nav>

      <div className="mt-auto border-t border-line p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-xs uppercase tracking-wide text-muted">
            Members · {members.length}
          </p>
          {ws.role === "owner" && (
            <Button size="sm" variant="secondary" onClick={onInvite}>
              Invite
            </Button>
          )}
        </div>
        {inviteUrl && (
          <input
            readOnly
            value={inviteUrl}
            onFocus={(e) => e.currentTarget.select()}
            className="mb-3 w-full truncate rounded-md border border-line bg-surface-2 px-2 py-1 text-xs text-cyan"
          />
        )}
        <ul className="space-y-2">
          {members.map((m) => (
            <li key={m.user_id} className="flex items-center gap-2">
              <Avatar email={m.email} size={26} />
              <span className="truncate text-sm text-muted">{m.email}</span>
              <span className="ml-auto text-[10px] capitalize text-muted/70">
                {m.role}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

export function WorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const [ws, setWs] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [prompt, setPrompt] = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!id) return;
    Promise.all([api.getWorkspace(id), api.listMembers(id)])
      .then(([w, m]) => {
        setWs(w);
        setMembers(m);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Failed to load.")
      );
  }, [id]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages]);

  async function onInvite() {
    if (!id) return;
    try {
      const inv = await api.createInvite(id);
      setInviteUrl(inv.url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Invite failed.");
    }
  }

  async function onSend(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim() || streaming) return;
    const text = prompt.trim();
    setPrompt("");
    setMessages((m) => [
      ...m,
      { role: "user", text },
      { role: "assistant", text: "", streaming: true },
    ]);
    setStreaming(true);
    try {
      await streamChat(text, (chunk) =>
        setMessages((m) => {
          const next = [...m];
          next[next.length - 1] = {
            ...next[next.length - 1],
            text: next[next.length - 1].text + chunk,
          };
          return next;
        })
      );
    } finally {
      setMessages((m) => {
        const next = [...m];
        next[next.length - 1] = { ...next[next.length - 1], streaming: false };
        return next;
      });
      setStreaming(false);
    }
  }

  if (error) {
    return (
      <div className="flex h-full flex-col">
        <Topbar />
        <div className="grid flex-1 place-items-center text-danger">{error}</div>
      </div>
    );
  }
  if (!ws) return <FullPageSpinner />;

  return (
    <div className="flex h-full flex-col">
      <Topbar />
      <div className="flex min-h-0 flex-1">
        <Sidebar
          ws={ws}
          members={members}
          onInvite={onInvite}
          inviteUrl={inviteUrl}
        />

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-line px-5 py-3">
            <span className="font-medium tracking-tight"># general</span>
            <span className="rounded-full border border-cyan/40 bg-cyan/10 px-2 py-0.5 text-xs text-cyan">
              live streaming demo
            </span>
            <span className="ml-auto text-xs text-muted">
              persisted conversations land in M2
            </span>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-5">
            {messages.length === 0 && (
              <div className="mx-auto mt-16 max-w-md text-center">
                <p className="text-helix text-lg font-semibold">
                  Start the conversation
                </p>
                <p className="mt-2 text-sm text-muted">
                  Send a prompt and watch the reply stream in. This panel proves
                  the React → FastAPI → provider stream end-to-end.
                </p>
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={m.role === "user" ? "flex justify-end" : "flex"}
              >
                <div
                  className={
                    "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed " +
                    (m.role === "user"
                      ? "gradient-helix text-[#0A0A12]"
                      : "border border-line bg-surface")
                  }
                >
                  <span className={m.streaming ? "caret" : ""}>{m.text}</span>
                </div>
              </div>
            ))}
          </div>

          <form
            onSubmit={onSend}
            className="flex items-center gap-3 border-t border-line p-4"
          >
            <input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ask anything…"
              className="flex-1 rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-sm text-fg placeholder:text-muted/60 focus:border-violet/60 focus:outline-none focus:ring-2 focus:ring-violet/30"
            />
            <Button type="submit" loading={streaming}>
              Send
            </Button>
          </form>
        </main>
      </div>
    </div>
  );
}
