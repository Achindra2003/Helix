import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listConversations, createConversation, listBranches, getHistory, forkBranch, getHealth, downloadExport,
  listReferences, addReference, removeReference, listMembers, getProviderSettings, downloadReport,
  deleteLastMessage, renameConversation, deleteConversation, renameBranch, deleteBranch, getToolSettings,
  searchWorkspace, resolveBranch, voteBranch, concludeConversation, postNote,
} from "@/lib/api";
import { streamSSE } from "@/lib/sse";
import { onRoomEvent, sendViewing, sendDrafting } from "@/lib/realtime";
import type { Branch, BranchStatus, Conversation, ConversationRef, GroundingItem, Node, RunEvent, WorkspaceSearchHit } from "@/lib/types";
import { useSession, useEffectiveRole } from "@/store/session";
import { STATE } from "@/lib/glyphs";
import { useMonitor } from "@/store/monitor";
import { usePendingInsert } from "@/store/insert";
import { usePresenceStore } from "@/store/presence";
import { useUnread } from "@/store/unread";
import { can } from "@/lib/rbac";
import { activatable } from "@/lib/a11y";
import { colorFor, nowTime } from "@/lib/format";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Dialog } from "@/components/common/Dialog";
import { Input, Field } from "@/components/common/Input";
import { EmptyState } from "@/components/common/Feedback";
import { Frontispiece } from "@/components/brand/Frontispiece";
import { ConversationList } from "@/components/chat/ConversationList";
import { BranchTree } from "@/components/chat/BranchTree";
import { MessageList, type ChatMessage, type ToolActivity } from "@/components/chat/MessageList";
import { Composer } from "@/components/chat/Composer";
import { DeepReasoningMonitor } from "@/components/monitor/DeepReasoningMonitor";
import { ReplayBar } from "@/components/chat/ReplayBar";
import { TeamStrip } from "@/components/chat/TeamStrip";
import { type ThreadAction } from "@/components/chat/ThreadMenu";
import { StageHeader } from "@/components/chat/StageHeader";
import { useAgentRun, compactArgs } from "@/components/chat/useAgentRun";
import { ForkDialog, ConcludeDialog, ResolveDialog, LinkContextDialog } from "@/components/chat/dialogs";
import { useDeepRun, pickText } from "@/components/chat/useDeepRun";
import s from "@/components/chat/chat.module.css";

// Citations are persisted on the node now and arrive with the history, so the
// server is the source of truth. This map survives as a *live overlay only*:
// during a run the sources are announced before the assistant node exists, so
// there is a window with chips on screen and no node to hang them on. Once the
// node arrives its own `citations` win.
//
// It used to be the only place citations existed anywhere — which meant a
// reload silently dropped the evidence for every grounded answer in the thread.
const groundingByNode: Record<string, GroundingItem[]> = {};
// Same deal for the agent tool ledger (FR-14): which tools each reply used.
const toolsByNode: Record<string, ToolActivity[]> = {};
// Whether the Deep Reasoning pane is unfolded. Per browser, not per workspace:
// it's a preference about how you like the stage laid out.
const MONITOR_PREF = "helix.monitorOpen";

function nodeToMsg(
  n: Node,
  meId: string | undefined,
  forkNodeId: string | null,
  emailOf?: (id: string | null) => string | undefined,
  forkMap?: Record<string, string[]>,
): ChatMessage {
  const email = emailOf?.(n.author_id);
  return {
    id: n.id,
    role: n.role,
    authorName: n.role === "assistant" ? "Helix" : n.author_id === meId ? "You" : (email ?? "teammate"),
    authorColor: n.role === "assistant" ? undefined : colorFor(email ?? n.author_id ?? "?"),
    body: n.content,
    time: "",
    // "~" because it is a ~4-chars-per-token estimate, not a tokenizer count —
    // the same estimator the context budget spends. Stating a measured-looking
    // number we did not measure is the kind of small lie a record shouldn't tell.
    tokens: n.token_count ? `~${n.token_count} tokens` : undefined,
    forkPoint: !!forkNodeId && n.id === forkNodeId,
    forkChildren: forkMap?.[n.id],
    grounding: n.citations?.length ? n.citations : groundingByNode[n.id],
    tools: toolsByNode[n.id],
  };
}

export function ChatView() {
  const { wid } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { push } = useToast();
  const user = useSession((st) => st.user);
  const role = useEffectiveRole();
  const monitor = useMonitor();
  const { promptId: pendingPrompt, clear: clearPending } = usePendingInsert();

  const canSend = can(role, "message.send");
  const canFork = can(role, "branch.fork");
  // The one write an Observer has. True for everyone, so it never gates the
  // full composer — it only decides whether the read-only view gets one too.
  const canNote = can(role, "note.write");

  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [activeBranchId, setActiveBranchId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState("groq");
  const [forkDlg, setForkDlg] = useState<{ nodeId: string } | null>(null);
  const [newDlg, setNewDlg] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftVis, setDraftVis] = useState<"shared" | "private">("shared");
  const [replay, setReplay] = useState<number | null>(null);
  // Below 1100px the flanking panes fold out over the stage instead of being
  // hidden; one at a time, since they enter from opposite edges.
  const [drawer, setDrawer] = useState<"left" | "monitor" | null>(null);
  // Wide layouts: the monitor folds to a spine so the stage takes back its
  // width. Remembered, because a pane that reopens itself every visit is a pane
  // you have to dismiss every visit.
  //
  // It starts folded. Open was the old default, and it meant a fifth of the
  // workspace was reserved, permanently, for a pane that reads "The monitor is
  // quiet" in every session where nobody escalates anything — which is most of
  // them. Folded it is still a labelled spine carrying the run's status, so the
  // feature is not hidden, and the effect below opens it the instant a run
  // starts, which is the only moment the pane has something to say.
  const [monitorOpen, setMonitorOpen] = useState(() => {
    try { return localStorage.getItem(MONITOR_PREF) === "1"; } catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem(MONITOR_PREF, monitorOpen ? "1" : "0"); } catch { /* private mode */ }
  }, [monitorOpen]);
  // A run the reader cannot see is the one thing folding must never cause —
  // including a teammate's run arriving over the room socket, which is exactly
  // the moment this product exists for.
  const st = monitor.run?.status;
  const monitorRunning = st === "queued" || st === "live" || st === "waiting";
  useEffect(() => {
    if (monitorRunning) setMonitorOpen(true);
  }, [monitorRunning]);
  const [linkDlg, setLinkDlg] = useState(false);
  // "Edit last message" hand-off: the removed message's text, waiting in the
  // composer for the author to revise and resend.
  const [composerDraft, setComposerDraft] = useState<string | null>(null);
  // Conversation/branch housekeeping dialogs.
  const [renameDlg, setRenameDlg] = useState<{ kind: "conversation" | "branch"; id: string; name: string } | null>(null);
  const [deleteDlg, setDeleteDlg] = useState<{ kind: "conversation" | "branch"; id: string; name: string } | null>(null);
  // Recording what came of an exploration (adopted / abandoned / reopened).
  const [resolveDlg, setResolveDlg] = useState<Branch | null>(null);
  const [concludeDlg, setConcludeDlg] = useState(false);

  // The thread on screen is by definition read — keep its unread marker clear
  // even as live turns stream into it.
  const unreadIds = useUnread((st) => st.ids);
  useEffect(() => {
    if (activeConvId) useUnread.getState().clear(activeConvId);
  }, [activeConvId, messages.length]);
  const canvasRef = useRef<HTMLDivElement>(null);
  // Which branch is on screen *now* — deep runs finish asynchronously (maybe
  // after a branch switch or a reload), so history refreshes check this first.
  const activeBranchRef = useRef<string | null>(null);
  useEffect(() => { activeBranchRef.current = activeBranchId; }, [activeBranchId]);
  // Same for the conversation: the resurfacing debounce fires later than the
  // keystroke that armed it, and must exclude the thread on screen *then*
  // (typing right after a switch would otherwise exclude the wrong thread).
  const activeConvRef = useRef<string | null>(null);
  useEffect(() => { activeConvRef.current = activeConvId; }, [activeConvId]);

  // Deep link from the Map, the search overlay, or the notification bell:
  // /w/:wid?conv=…&branch=… lands directly in that thread at that branch.
  // Watches param *changes* (not just mount) so navigating from search/bell
  // works while this view is already open. Consumed, then removed from the URL.
  const [searchParams, setSearchParams] = useSearchParams();
  const wantedBranchRef = useRef<string | null>(searchParams.get("branch"));
  useEffect(() => {
    const conv = searchParams.get("conv");
    if (!conv) return;
    const branch = searchParams.get("branch");
    if (conv === activeConvId) {
      // Same conversation: the branch-loading effect won't rerun — switch directly.
      if (branch) setActiveBranchId(branch);
    } else {
      wantedBranchRef.current = branch;
      setActiveConvId(conv);
    }
    setSearchParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Presence: tell the room which branch we're reading (Map dots, row dots).
  useEffect(() => { sendViewing(activeBranchId, activeConvId); }, [activeBranchId, activeConvId]);
  useEffect(() => () => sendViewing(null), []);

  const { data: convData } = useQuery({
    queryKey: ["conversations", wid, user?.id],
    queryFn: () => listConversations(wid!),
    enabled: !!wid,
  });
  const conversations: Conversation[] = convData?.items ?? [];
  const activeConv = conversations.find((c) => c.id === activeConvId) ?? null;
  const activeBranch = branches.find((b) => b.id === activeBranchId) ?? null;

  // Members: resolve author ids to emails so multi-author threads read as
  // people, and colors stay consistent with the Map's presence dots.
  const { data: memberData } = useQuery({
    queryKey: ["members", wid],
    queryFn: () => listMembers(wid!),
    enabled: !!wid,
  });
  const emailOf = (id: string | null) =>
    id === user?.id ? user?.email : memberData?.find((m) => m.user_id === id)?.email;

  // BYO-key status: a keyless workspace gets a "plug in a key" nudge instead
  // of a composer that dies with an opaque error on first send.
  const { data: providerSettings } = useQuery({
    queryKey: ["provider-settings", wid],
    queryFn: () => getProviderSettings(wid!),
    enabled: !!wid,
  });
  const providerUnconfigured = providerSettings ? !providerSettings.configured : false;

  // Agent runs (FR-14): what this workspace's agent may do — for the composer
  // tooltip, and to warn that sensitive calls will pause for approval.
  const { data: toolSettings } = useQuery({
    queryKey: ["tool-settings", wid],
    queryFn: () => getToolSettings(wid!),
    enabled: !!wid,
  });
  const agentHint = useMemo(() => {
    if (!toolSettings) return undefined;
    const usable = toolSettings.items.filter((t) => t.allowed && t.available);
    if (usable.length === 0) {
      return "Agent: no tools enabled in this workspace — owners can enable them under SETUP → Agent tools";
    }
    const names = usable.map((t) => t.name).join(", ");
    return `Agent: Helix may use ${names}${usable.some((t) => t.sensitive) ? " — sensitive calls pause for your approval" : ""}`;
  }, [toolSettings]);

  // The agent turn lives in its own controller — it is the most stateful thing
  // this surface does, and it kept the interesting parts of this file buried.
  const { approval, runAgent, decideApproval } = useAgentRun({
    setMessages, scrollDown, setBusy,
    onSettled: () => {
      if (activeConvId) listBranches(activeConvId).then((r) => setBranches(r.items)).catch(() => {});
      qc.invalidateQueries({ queryKey: ["conversations", wid] });
    },
    groundingByNode, toolsByNode,
  });

  async function onAgent(text: string) {
    const branchId = await ensureConversation();
    if (!branchId) return;
    await runAgent(text, branchId, colorFor(user?.email ?? "?"), nowTime());
  }

  // Proactive resurfacing: while a question is being typed, quietly check
  // whether the workspace has already explored it — the product's whole
  // thesis ("nobody re-asks what a colleague solved") made visible at the
  // exact moment it matters. Debounced; gated hard on relevance (this is
  // unsolicited UI — the same lesson as RAG's citation gate: silence beats
  // noise); an enhancement, so failures never surface.
  // Floor calibrated on real MiniLM cosines: related rephrasings of the same
  // question score 0.37–0.48, adjacent-but-different topics 0.27, unrelated
  // ≤0.11 — 0.33 splits related from adjacent with margin on both sides.
  // (Stricter than the 0.20 document-grounding floor because this surface is
  // unsolicited: a wrong chip here is noise, not a wrong citation.)
  const RESURFACE_FLOOR = 0.33;
  const [resurfaced, setResurfaced] = useState<WorkspaceSearchHit[]>([]);
  const [resurfaceMuted, setResurfaceMuted] = useState(false);
  const resurfaceTimer = useRef<number | null>(null);
  const resurfaceSeq = useRef(0);
  useEffect(() => () => { if (resurfaceTimer.current) window.clearTimeout(resurfaceTimer.current); }, []);
  // A new thread on screen is a new question context — reset the strip, and
  // stop telling the room I am drafting in the thread I just left.
  useEffect(() => {
    setResurfaced([]);
    setResurfaceMuted(false);
    sendDrafting(null, false);
    return () => sendDrafting(null, false);
  }, [activeConvId]);

  function onDraftChange(text: string) {
    if (resurfaceTimer.current) window.clearTimeout(resurfaceTimer.current);
    const q = text.trim();
    if (q.length < 18) {
      // Too short to mean anything (and "" is a send/clear): drop the strip
      // and un-mute for the next question.
      setResurfaced([]);
      setResurfaceMuted(false);
      sendDrafting(null, false);
      return;
    }
    resurfaceTimer.current = window.setTimeout(async () => {
      const seq = ++resurfaceSeq.current;
      try {
        const r = await searchWorkspace(wid!, q, 8);
        if (seq !== resurfaceSeq.current) return; // a newer draft superseded this
        const seen = new Set<string>();
        setResurfaced(r.items.filter((h) => {
          if (h.conversation_id === activeConvRef.current) return false; // it's on screen
          if (h.score < RESURFACE_FLOOR) return false;
          if (seen.has(h.conversation_id)) return false; // one chip per thread
          seen.add(h.conversation_id);
          return true;
        }).slice(0, 3));
        // Tell the room the same thing this strip just told me: a question is
        // being composed here, and it overlaps that thread. Ids only, and only
        // once the draft is long enough to have crossed the same relevance bar
        // the strip uses — the room should not light up for every keystroke.
        const top = r.items.find((h) => h.score >= RESURFACE_FLOOR && h.conversation_id !== activeConvRef.current);
        sendDrafting(activeConvRef.current, true, top?.conversation_id ?? null);
      } catch { /* resurfacing is an enhancement, never an error */ }
    }, 700);
  }

  // Teammates reading each conversation right now (dots on the rows).
  const presenceUsers = usePresenceStore((st) => st.users);
  const conversationViewers = useMemo(() => {
    const map: Record<string, { email: string }[]> = {};
    for (const u of presenceUsers) {
      if (!u.viewing_conversation || u.user_id === user?.id) continue;
      (map[u.viewing_conversation] ??= []).push({ email: u.email });
    }
    return map;
  }, [presenceUsers, user?.id]);

  // The room dock: teammates composing a question right now, in a thread I can
  // see. The socket carries ids only, so a title appears here only because it
  // is already in MY conversation list — a thread I cannot see resolves to
  // nothing and the line is dropped rather than half-rendered.
  const roomDrafts = useMemo(() => {
    const byId = new Map(conversations.map((c) => [c.id, c]));
    return presenceUsers.flatMap((u) => {
      if (u.user_id === user?.id || !u.drafting_conversation) return [];
      const where = byId.get(u.drafting_conversation);
      if (!where) return [];
      const match = u.drafting_match ? byId.get(u.drafting_match) ?? null : null;
      return [{ email: u.email, where, match }];
    });
  }, [presenceUsers, conversations, user?.id]);

  // Link the overlapping thread onto the conversation THEY are drafting in, so
  // the context is already folded in when they press send. This is the whole
  // point of the dock: the answer to "has someone been here before" arrives
  // before the question is asked, not after.
  async function doLinkFor(targetConvId: string, refId: string) {
    try {
      await addReference(targetConvId, refId);
      await qc.invalidateQueries({ queryKey: ["references", targetConvId] });
      push("Linked for them — their next reply draws on that thread");
    } catch (e: any) { push(e?.message ?? "Link failed", "error"); }
  }

  // While a teammate's turn streams into the open branch, name them above the
  // composer ("you can see each other think").
  const [remoteAuthorId, setRemoteAuthorId] = useState<string | null>(null);

  // node id -> names of branches forked from it (always-visible margin glyphs).
  const forkSourceMap = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const b of branches) if (b.fork_node_id) (map[b.fork_node_id] ??= []).push(b.name);
    return map;
  }, [branches]);

  // Cross-conversation references: other shared threads whose live context is
  // folded into this conversation's replies. Re-fetched per active conversation.
  const { data: refData } = useQuery({
    queryKey: ["references", activeConvId],
    queryFn: () => listReferences(activeConvId!),
    enabled: !!activeConvId,
  });
  const references: ConversationRef[] = refData?.items ?? [];

  async function doAddRef(refId: string) {
    if (!activeConvId) return;
    try {
      await addReference(activeConvId, refId);
      await qc.invalidateQueries({ queryKey: ["references", activeConvId] });
      push("Context linked — replies here now draw on that thread");
    } catch (e: any) { push(e?.message ?? "Link failed", "error"); }
  }
  async function doRemoveRef(refId: string) {
    if (!activeConvId) return;
    try {
      await removeReference(activeConvId, refId);
      await qc.invalidateQueries({ queryKey: ["references", activeConvId] });
    } catch (e: any) { push(e?.message ?? "Unlink failed", "error"); }
  }

  useEffect(() => { getHealth().then((h) => setProvider(h.provider)).catch(() => {}); }, []);

  // pick a conversation once the list loads
  useEffect(() => {
    if (!activeConvId && conversations.length) setActiveConvId(conversations[0].id);
  }, [conversations, activeConvId]);

  // load branches when the active conversation changes
  useEffect(() => {
    if (!activeConvId) { setBranches([]); setActiveBranchId(null); return; }
    let alive = true;
    listBranches(activeConvId).then((r) => {
      if (!alive) return;
      setBranches(r.items);
      // A Map deep-link may name a branch; otherwise open the main spine.
      const wanted = wantedBranchRef.current;
      wantedBranchRef.current = null;
      const pick =
        (wanted && r.items.find((b) => b.id === wanted)) ||
        r.items.find((b) => b.parent_branch_id === null) || r.items[0];
      setActiveBranchId(pick?.id ?? null);
    }).catch(() => {});
    return () => { alive = false; };
  }, [activeConvId]);

  // load history when the active branch changes
  useEffect(() => {
    if (!activeBranchId) { setMessages([]); return; }
    let alive = true;
    setReplay(null);
    getHistory(activeBranchId).then((r) => {
      if (!alive) return;
      setMessages(r.nodes.map((n) => nodeToMsg(n, user?.id, activeBranch?.fork_node_id ?? null, emailOf, forkSourceMap)));
    }).catch(() => {});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeBranchId, memberData, forkSourceMap]);

  function scrollDown() {
    requestAnimationFrame(() => { if (canvasRef.current) canvasRef.current.scrollTop = canvasRef.current.scrollHeight; });
  }

  async function doNewConversation(title: string, visibility: "shared" | "private" = "shared") {
    if (!wid) return;
    try {
      const r = await createConversation(wid, title || "Untitled", visibility);
      await qc.invalidateQueries({ queryKey: ["conversations", wid] });
      setActiveConvId(r.conversation_id);
      setActiveBranchId(r.branch_id);
      setBranches([{ id: r.branch_id, conversation_id: r.conversation_id, name: "main", parent_branch_id: null, fork_node_id: null, head_node_id: null, intent: "", status: "open", resolution: "", resolved_by: null, resolved_at: null, votes: [] }]);
      setMessages([]);
    } catch (e: any) { push(e?.message ?? "Create failed", "error"); }
  }

  async function ensureConversation(): Promise<string | null> {
    if (activeBranchId) return activeBranchId;
    if (!wid) return null;
    const r = await createConversation(wid, "Untitled", "shared");
    await qc.invalidateQueries({ queryKey: ["conversations", wid] });
    setActiveConvId(r.conversation_id);
    setActiveBranchId(r.branch_id);
    setBranches([{ id: r.branch_id, conversation_id: r.conversation_id, name: "main", parent_branch_id: null, fork_node_id: null, head_node_id: null, intent: "", status: "open", resolution: "", resolved_by: null, resolved_at: null, votes: [] }]);
    return r.branch_id;
  }

  async function streamTurn(branchId: string, path: string, body: unknown) {
    setBusy(true);
    const userMsg: ChatMessage = { id: "tmp-u", role: "user", authorName: "You", authorColor: colorFor(user?.email ?? "?"), body: typeof (body as any).prompt === "string" ? (body as any).prompt : "(inserted prompt)", time: nowTime() };
    const asstMsg: ChatMessage = { id: "tmp-a", role: "assistant", authorName: "Helix", body: "", time: nowTime(), typing: true };
    setMessages((m) => [...m, userMsg, asstMsg]);
    scrollDown();
    let acc = "";
    try {
      const h = streamSSE(path, body, (ev) => {
        if (ev.kind === "user_node") {
          userMsg.id = ev.node.id; userMsg.body = ev.node.content;
          setMessages((m) => [...m]);
        } else if (ev.kind === "grounding") {
          // Emitted before the reply's tokens when workspace documents cleared
          // the relevance gate — pin the source chips on the incoming reply.
          asstMsg.grounding = ev.items;
          setMessages((m) => [...m]);
        } else if (ev.kind === "token") {
          acc += ev.text; asstMsg.body = acc; setMessages((m) => [...m]); scrollDown();
        } else if (ev.kind === "assistant_node") {
          asstMsg.id = ev.node.id; asstMsg.typing = false;
          asstMsg.tokens = ev.node.token_count ? `${ev.node.token_count} tokens · ${provider}` : undefined;
          if (asstMsg.grounding) groundingByNode[ev.node.id] = asstMsg.grounding;
        }
      });
      await h.done;
    } catch (e: any) {
      asstMsg.body = acc + `\n[stream error: ${e?.message ?? e}]`;
    }
    asstMsg.typing = false;
    setMessages((m) => [...m]);
    setBusy(false);
    // refresh branch head + conversation meta
    listBranches(activeConvId!).then((r) => setBranches(r.items)).catch(() => {});
    qc.invalidateQueries({ queryKey: ["conversations", wid] });
  }

  async function onSend(text: string) {
    const branchId = await ensureConversation();
    if (!branchId) return;
    if (messages.length === 0) setMessages([]);
    await streamTurn(branchId, `/conversations/${branchId}/messages`, { prompt: text });
  }

  async function onInsertPrompt(promptId: string) {
    const branchId = await ensureConversation();
    if (!branchId) return;
    await streamTurn(branchId, `/conversations/${branchId}/messages/from-prompt`, { prompt_id: promptId });
  }


  // consume a pending "insert from library" once we're in chat
  useEffect(() => {
    if (pendingPrompt && activeBranchId) {
      const id = pendingPrompt; clearPending();
      onInsertPrompt(id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPrompt, activeBranchId]);

  // Delete/edit is offered only on the branch's trailing turn, only to its
  // author, and only outside replay — the server independently enforces the
  // author gate and refuses once anything has forked from the turn.
  const lastTurn = useMemo(() => {
    if (replay !== null || busy || messages.length === 0 || !canSend) return undefined;
    const tail = messages[messages.length - 1];
    const userMsg = tail.role === "user" ? tail
      : tail.role === "assistant" ? messages[messages.length - 2] : undefined;
    if (!userMsg || userMsg.role !== "user" || userMsg.authorName !== "You") return undefined;
    if (tail.typing || userMsg.typing || userMsg.id.startsWith("tmp-")) return undefined;
    return userMsg;
  }, [messages, replay, busy, canSend]);

  async function removeLastTurn(): Promise<boolean> {
    if (!activeBranchId) return false;
    try {
      await deleteLastMessage(activeBranchId);
      const r = await getHistory(activeBranchId);
      setMessages(r.nodes.map((n) => nodeToMsg(n, user?.id, activeBranch?.fork_node_id ?? null, emailOf, forkSourceMap)));
      listBranches(activeConvId!).then((b) => setBranches(b.items)).catch(() => {});
      return true;
    } catch (e: any) {
      push(e?.message ?? "Delete failed", "error");
      return false;
    }
  }

  async function onDeleteLast() {
    if (await removeLastTurn()) push("Last exchange removed");
  }

  async function onEditLast() {
    const text = lastTurn?.body ?? "";
    if (await removeLastTurn()) setComposerDraft(text);
  }

  async function doFork(nodeId: string, name: string, intent: string) {
    if (!activeConvId) return;
    try {
      const r = await forkBranch(activeConvId, nodeId, name || "experiment", intent);
      const tree = await listBranches(activeConvId);
      setBranches(tree.items);
      setActiveBranchId(r.branch_id);
      push(`Forked → ${r.name}`);
    } catch (e: any) { push(e?.message ?? "Fork failed", "error"); }
  }

  async function doNote(text: string) {
    const branchId = await ensureConversation();
    if (!branchId) return;
    try {
      const node = await postNote(branchId, text);
      setMessages((m) => [...m, nodeToMsg(node, user?.id, null, emailOf, forkSourceMap)]);
      scrollDown();
    } catch (e: any) { push(e?.message ?? "Could not post that", "error"); }
  }

  // What moved out of the stage header. Replay is a *mode*, so it earns space
  // only while it is on; the exports and the housekeeping are rare enough that
  // one click is the right price for a header you can read.
  const threadActions: ThreadAction[] = useMemo(() => {
    if (!activeConv) return [];
    const out: ThreadAction[] = [];
    if (messages.length > 0) {
      out.push({
        key: "replay", glyph: "▷", label: "Replay this thread",
        onPick: () => setReplay(1),
      });
      // The report first, and named for what it answers. It is the whole
      // thread — every exploration including the abandoned ones, each verdict
      // with its reason — where the two below are one branch's transcript.
      // Someone who wants "what did we decide, and why" wants this one, and
      // before it existed the only thing they could take away was a single
      // path with the alternative missing.
      out.push({
        key: "report", glyph: "❧", label: "Export decision report",
        onPick: () => downloadReport(activeConv.id, "md")
          .catch(() => push("Export failed", "error")),
      });
      out.push({
        key: "md", glyph: "↓", label: "Export this branch (Markdown)",
        onPick: () => downloadExport(activeConv.id, activeBranchId!, "md")
          .catch(() => push("Export failed", "error")),
      });
      out.push({
        key: "json", glyph: "↓", label: "Export this branch (JSON)",
        onPick: () => downloadExport(activeConv.id, activeBranchId!, "json")
          .catch(() => push("Export failed", "error")),
      });
    }
    if (canSend) {
      out.push({
        key: "link", glyph: STATE.linked, label: "Link another thread's context",
        onPick: () => setLinkDlg(true),
      });
    }
    if (activeConv.author_id === user?.id || role === "owner") {
      out.push({
        key: "rename", glyph: "✎", label: "Rename conversation",
        onPick: () => setRenameDlg({ kind: "conversation", id: activeConv.id, name: activeConv.title }),
      });
      out.push({
        key: "delete", glyph: "✕", label: "Delete conversation", danger: true,
        onPick: () => setDeleteDlg({ kind: "conversation", id: activeConv.id, name: activeConv.title }),
      });
    }
    return out;
  }, [activeConv, activeBranchId, messages.length, canSend, role, user?.id]);

  async function doConclude(text: string) {
    if (!activeConvId) return;
    try {
      await concludeConversation(activeConvId, text);
      await qc.invalidateQueries({ queryKey: ["conversations", wid] });
      push(text ? "Conclusion recorded" : "Conclusion cleared — the question is open again");
    } catch (e: any) { push(e?.message ?? "Could not record that", "error"); }
  }

  async function doResolve(branchId: string, status: BranchStatus, resolution: string) {
    try {
      await resolveBranch(branchId, status, resolution);
      if (activeConvId) setBranches((await listBranches(activeConvId)).items);
      push(status === "open" ? "Reopened — verdict cleared" : `Recorded as ${status}`);
    } catch (e: any) { push(e?.message ?? "Could not record that", "error"); }
  }

  async function doVote(branchId: string) {
    // Optimistic: backing a branch is a one-click opinion, and a chip that
    // waits for a round trip before filling reads as an unregistered click.
    // The server's tally replaces this either way, so a failed request
    // self-corrects on the refetch below.
    const me = user?.id;
    if (me) {
      setBranches((bs) => bs.map((b) => b.id !== branchId ? b : {
        ...b,
        votes: b.votes?.includes(me)
          ? b.votes.filter((v) => v !== me)
          : [...(b.votes ?? []), me],
      }));
    }
    try {
      await voteBranch(branchId);
      if (activeConvId) setBranches((await listBranches(activeConvId)).items);
    } catch (e: any) {
      if (activeConvId) setBranches((await listBranches(activeConvId)).items);
      push(e?.message ?? "Could not record that", "error");
    }
  }

  async function doRename() {
    if (!renameDlg) return;
    const name = renameDlg.name.trim();
    if (!name) return;
    try {
      if (renameDlg.kind === "conversation") {
        await renameConversation(renameDlg.id, name);
        await qc.invalidateQueries({ queryKey: ["conversations", wid] });
      } else {
        await renameBranch(renameDlg.id, name);
        if (activeConvId) setBranches((await listBranches(activeConvId)).items);
      }
      setRenameDlg(null);
      push("Renamed");
    } catch (e: any) { push(e?.message ?? "Rename failed", "error"); }
  }

  async function doDelete() {
    if (!deleteDlg) return;
    try {
      if (deleteDlg.kind === "conversation") {
        await deleteConversation(deleteDlg.id);
        await qc.invalidateQueries({ queryKey: ["conversations", wid] });
        if (deleteDlg.id === activeConvId) { setActiveConvId(null); setActiveBranchId(null); }
        push("Conversation deleted");
      } else {
        await deleteBranch(deleteDlg.id);
        if (activeConvId) {
          const tree = await listBranches(activeConvId);
          setBranches(tree.items);
          if (deleteDlg.id === activeBranchId) {
            const main = tree.items.find((b) => b.parent_branch_id === null) ?? tree.items[0];
            setActiveBranchId(main?.id ?? null);
          }
        }
        push("Branch deleted");
      }
      setDeleteDlg(null);
    } catch (e: any) { push(e?.message ?? "Delete failed", "error"); }
  }

  // Deep Reasoning's whole lifecycle — segmented streams, steering, killing,
  // and reattaching to a run that outlived the last page load. The view keeps
  // ownership of the transcript, so the hook asks for a refresh rather than
  // learning how to build one.
  const { onDeep, stopRun } = useDeepRun({
    wid, role, activeConvId, ensureConversation,
    isViewing: (branchId) => activeBranchRef.current === branchId,
    refreshHistory: (branchId) => {
      getHistory(branchId).then((r) => setMessages(
        r.nodes.map((n) => nodeToMsg(n, user?.id, activeBranch?.fork_node_id ?? null, emailOf, forkSourceMap)),
      )).catch(() => {});
    },
  });

  // --- Live fan-out (FR-5): teammates' activity arrives over the workspace
  // room. A turn streaming on the branch I'm viewing renders in place,
  // token-by-token, exactly like my own; anything else refreshes the lists.
  // A teammate's Deep Reason run even lights up my monitor (watch-only) when
  // mine is idle.
  const remoteRuns = useRef<Map<string, { asst: ChatMessage; acc: string; watching: boolean }>>(new Map());
  useEffect(() => {
    remoteRuns.current.clear();
    setRemoteAuthorId(null);
    const off = onRoomEvent((ev) => {
      if (ev.kind === "conversation.created" || ev.kind === "conversation.updated") {
        qc.invalidateQueries({ queryKey: ["conversations", wid] });
      } else if (ev.kind === "conversation.deleted") {
        qc.invalidateQueries({ queryKey: ["conversations", wid] });
        if (ev.conversation_id === activeConvId) {
          // The thread I was reading is gone — fall back to the list.
          setActiveConvId(null);
          setActiveBranchId(null);
        }
      } else if (ev.kind === "branch.created" || ev.kind === "branch.updated") {
        if (ev.conversation_id === activeConvId) {
          listBranches(activeConvId).then((r) => setBranches(r.items)).catch(() => {});
        }
      } else if (ev.kind === "note.posted") {
        if (ev.branch_id === activeBranchId) {
          setMessages((m) => m.some((x) => x.id === ev.node.id)
            ? m
            : [...m, nodeToMsg(ev.node, user?.id, null, emailOf, forkSourceMap)]);
          scrollDown();
        }
      } else if (ev.kind === "branch.resolved") {
        if (ev.conversation_id === activeConvId) {
          listBranches(activeConvId).then((r) => setBranches(r.items)).catch(() => {});
          // Say it out loud when it lands on the branch someone is reading:
          // continuing to explore something the team just abandoned is exactly
          // the wasted work this product exists to prevent.
          if (ev.branch_id === activeBranchId && ev.status !== "open") {
            push(`“${ev.name}” was ${ev.status} — ${ev.resolution}`);
          }
        }
      } else if (ev.kind === "branch.voted") {
        // No toast. A vote is a small, frequent signal — announcing each one
        // would make converging noisier than the forking it exists to settle.
        // The tally updating in place is the whole notification.
        if (ev.conversation_id === activeConvId) {
          setBranches((bs) => bs.map((b) =>
            b.id === ev.branch_id ? { ...b, votes: ev.votes ?? [] } : b));
        }
      } else if (ev.kind === "branch.deleted") {
        if (ev.conversation_id === activeConvId) {
          listBranches(activeConvId).then((r) => {
            setBranches(r.items);
            if (ev.branch_id === activeBranchId) {
              const main = r.items.find((b) => b.parent_branch_id === null) ?? r.items[0];
              setActiveBranchId(main?.id ?? null);
            }
          }).catch(() => {});
        }
      } else if (ev.kind === "references.updated") {
        if (ev.conversation_id === activeConvId) {
          qc.invalidateQueries({ queryKey: ["references", activeConvId] });
        }
      } else if (ev.kind === "messages.deleted") {
        // A teammate removed their trailing turn on the branch I'm reading —
        // reload so I'm not looking at messages that no longer exist.
        if (ev.branch_id === activeBranchId) {
          getHistory(ev.branch_id)
            .then((r) => setMessages(r.nodes.map((n) => nodeToMsg(n, user?.id, activeBranch?.fork_node_id ?? null, emailOf, forkSourceMap))))
            .catch(() => {});
        }
      } else if (ev.kind === "run_event") {
        if (ev.branch_id !== activeBranchId) return;
        const key = `${ev.author_id}:${ev.branch_id}`;
        const e = ev.event;
        let run = remoteRuns.current.get(key);
        if (e.kind === "user_node") {
          setRemoteAuthorId(ev.author_id);
          const authorEmail = emailOf(e.node.author_id);
          const userMsg: ChatMessage = {
            id: e.node.id, role: "user",
            authorName: authorEmail ?? "teammate",
            authorColor: colorFor(authorEmail ?? e.node.author_id ?? "?"),
            body: e.node.content, time: nowTime(),
          };
          const asst: ChatMessage = {
            id: `remote-${e.node.id}`, role: "assistant", authorName: "Helix",
            body: "", time: nowTime(), typing: true,
          };
          run = { asst, acc: "", watching: false };
          remoteRuns.current.set(key, run);
          setMessages((m) => [...m, userMsg, asst]);
          scrollDown();
        } else if (e.kind === "grounding" && run) {
          // Watchers get the same citation chips the author sees.
          run.asst.grounding = e.items;
          setMessages((m) => [...m]);
        } else if (e.kind === "token" && run) {
          run.acc += e.text;
          run.asst.body = run.acc;
          setMessages((m) => [...m]);
          scrollDown();
          if (run.watching) {
            const cur = useMonitor.getState().run;
            if (cur) monitor.patch({ answer: (cur.answer + e.text).replace(/^\s*\[answer\]\s*/i, "") });
          }
        } else if (e.kind === "tool_call" && run) {
          // A teammate's agent turn: watchers see the same tool ledger.
          (run.asst.tools ??= []).push({
            id: e.id, name: e.name, args: compactArgs(e.arguments),
            sensitive: e.sensitive, status: e.sensitive ? "pending" : "running",
          });
          setMessages((m) => [...m]);
        } else if (e.kind === "tool_result" && run) {
          const t = run.asst.tools?.find((x) => x.id === e.id && (x.status === "running" || x.status === "pending"));
          if (t) {
            t.status = e.status;
            t.preview = e.content;
            setMessages((m) => [...m]);
          }
        } else if (e.kind === "step" && run) {
          // A teammate escalated to Deep Reason on this branch: if my monitor
          // is idle, watch their reasoning trace live (no kill control — it's
          // their run).
          const cur = useMonitor.getState().run;
          if (!run.watching && (!cur || cur.status !== "live")) {
            run.watching = true;
            monitor.start({
              status: "live", question: `${STATE.watching} watching ${ev.author_id}'s deep run`,
              depth: 0, energy: 0, loopGuard: 0, stability: 0, confidence: 0,
              stabilityHistory: [],
              budgetPct: 0, tokensUsed: 0, steps: [], answer: "", stopReason: "",
              abort: () => {}, conversationId: ev.conversation_id, branchId: ev.branch_id,
              canControl: false, // their run, not mine
            });
          }
          if (run.watching) {
            const now = useMonitor.getState().run;
            if (now) {
              const p = e.payload ?? {};
              const num = (k: string, d: number) => (typeof p[k] === "number" ? (p[k] as number) : d);
              const stabNow = typeof p.stability === "number" ? (p.stability as number) : null;
              const thr = typeof p.stability_threshold === "number" ? (p.stability_threshold as number) : undefined;
              monitor.patch({
                depth: e.depth ?? now.depth, energy: e.energy ?? now.energy,
                loopGuard: num("loop_guard", now.loopGuard),
                stability: num("stability", now.stability),
                confidence: num("confidence", now.confidence),
                ...(stabNow !== null && stabNow !== now.stabilityHistory[now.stabilityHistory.length - 1]
                  ? { stabilityHistory: [...now.stabilityHistory, stabNow] } : {}),
                ...(thr !== undefined ? { threshold: thr } : {}),
              });
              monitor.addStep({ kind: e.node, meta: `step ${e.idx} · depth ${e.depth}`, text: pickText(p) });
            }
          }
        } else if (e.kind === "budget" && run?.watching) {
          const now = useMonitor.getState().run;
          if (now) monitor.patch({ budgetPct: Math.round(e.pct <= 1 ? e.pct * 100 : e.pct), tokensUsed: e.tokens_used ?? now.tokensUsed });
        } else if (e.kind === "complete" && run?.watching) {
          monitor.patch({ status: e.status === "killed" ? "killed" : e.status === "error" ? "error" : "done", stopReason: e.stop_reason });
        } else if (e.kind === "assistant_node" && run) {
          run.asst.id = e.node.id;
          run.asst.typing = false;
          run.asst.body = e.node.content || run.acc;
          run.asst.tokens = e.node.token_count ? `${e.node.token_count} tokens · ${provider}` : undefined;
          if (run.asst.grounding) groundingByNode[e.node.id] = run.asst.grounding;
          if (run.asst.tools?.length) toolsByNode[e.node.id] = run.asst.tools;
          setMessages((m) => [...m]);
        } else if (e.kind === "done") {
          remoteRuns.current.delete(key);
          setRemoteAuthorId(null);
          if (activeConvId) listBranches(activeConvId).then((r) => setBranches(r.items)).catch(() => {});
        }
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wid, activeConvId, activeBranchId]);

  const shownMessages = useMemo(
    () => (replay === null ? messages : messages.slice(0, replay)),
    [messages, replay],
  );

  // Escape closes an open drawer — the same reflex a dialog earns.
  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setDrawer(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer]);

  const runLive = monitor.run?.status === "live" || monitor.run?.status === "waiting";

  /** Same contract as the monitor's Stop: the run lives server-side, so the
   *  local stream being aborted is the fallback, not the mechanism. */
  return (
    <div className={`${s.grid} folio`} data-drawer={drawer ?? undefined}
      data-monitor={monitorOpen ? undefined : "collapsed"}>
      {/* LEFT */}
      <div className={s.left} id="chat-threads">
        <div className={s.scrollList}>
          <ConversationList
            conversations={conversations}
            activeId={activeConvId}
            canCreate={canSend}
            onSelect={(id) => { setActiveConvId(id); setDrawer(null); }}
            onNew={() => { setDraftTitle(""); setNewDlg(true); setDrawer(null); }}
            viewers={conversationViewers}
            unread={unreadIds}
          />
          {activeConv && branches.length > 0 && (
            <BranchTree branches={branches} activeId={activeBranchId} meId={user?.id}
              onSelect={(id) => { setActiveBranchId(id); setDrawer(null); }}
              onRename={canFork ? (b) => setRenameDlg({ kind: "branch", id: b.id, name: b.name }) : undefined}
              onDelete={canFork ? (b) => setDeleteDlg({ kind: "branch", id: b.id, name: b.name }) : undefined}
              onResolve={canFork ? (b) => setResolveDlg(b) : undefined}
              onVote={canFork ? (b) => doVote(b.id) : undefined} />
          )}
        </div>
        <div className={s.leftFoot}><span className={s.liveDot} /> live · server-ordered log</div>
      </div>

      {/* STAGE */}
      <div className={s.stage}>
        <div className={s.stageGeo}><Frontispiece size={560} animate={false} /></div>

        {/* The only route to the two panes below 1100px, so it sits outside the
            "a conversation is open" branch — otherwise the empty state would
            have no way to reach the thread list. */}
        <div className={s.drawerBar}>
          <button
            className={`${s.drawerBtn} ${drawer === "left" ? s.drawerBtnOn : ""}`}
            aria-expanded={drawer === "left"} aria-controls="chat-threads"
            onClick={() => setDrawer((d) => (d === "left" ? null : "left"))}
          >
            ⌇ threads
          </button>
          <div style={{ flex: 1 }} />
          <button
            className={`${s.drawerBtn} ${drawer === "monitor" ? s.drawerBtnOn : ""}`}
            aria-expanded={drawer === "monitor"} aria-controls="chat-monitor"
            onClick={() => setDrawer((d) => (d === "monitor" ? null : "monitor"))}
          >
            {runLive && <span className={s.drawerLive} />} ⟳ monitor
          </button>
        </div>
        {!activeConv ? (
          <EmptyState title="An unopened volume"
            icon={<div style={{ opacity: 0.45 }}><Frontispiece size={130} animate={false} /></div>}>
            {canSend ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
                <span>Every thread here is shared with the whole workspace — and any reply can be forked into its own branch.</span>
                <Button variant="primary" onClick={() => { setDraftTitle(""); setNewDlg(true); }}>Begin a conversation</Button>
              </div>
            ) : "Ask an Owner or Collaborator to start a thread."}
          </EmptyState>
        ) : (
          <>
            <StageHeader
              conversation={activeConv}
              branch={activeBranch}
              references={references}
              messageCount={messages.length}
              canSend={canSend}
              canFork={canFork}
              threadActions={threadActions}
              onConclude={() => setConcludeDlg(true)}
              onResolve={(b) => setResolveDlg(b)}
              onFork={() => activeBranch?.head_node_id
                ? setForkDlg({ nodeId: activeBranch.head_node_id })
                : push("Send a message before forking", "error")}
              onUnlinkRef={doRemoveRef}
              onOpenLedger={() => nav(`/w/${wid}/map?view=decisions`)}
            />

            {replay !== null && (
              <div className={s.replayBar}>
                <span className={s.replayLabel}>Replaying</span>
                <ReplayBar total={messages.length} value={replay} onChange={setReplay} />
                <div style={{ flex: 1 }} />
                <button className={s.teamMute} title="Leave replay"
                  onClick={() => setReplay(null)}>×</button>
              </div>
            )}
            <div className={s.canvas} ref={canvasRef}>
              {shownMessages.length === 0 ? (
                <EmptyState title="A blank page">
                  {canSend ? "Send the first message — the whole team shares this thread, and any reply can be forked into its own branch."
                           : "This thread is empty."}
                </EmptyState>
              ) : (
                <MessageList messages={shownMessages}
                  onForkHere={canFork ? (id) => setForkDlg({ nodeId: id }) : undefined}
                  lastTurn={lastTurn ? { userMsgId: lastTurn.id, onDelete: onDeleteLast, onEdit: onEditLast } : undefined} />
              )}
            </div>

            <div className={s.composerWrap}>
              <TeamStrip
                liveAuthor={remoteAuthorId ? (emailOf(remoteAuthorId) ?? "a teammate") : null}
                drafts={roomDrafts.map((d) => ({
                  email: d.email,
                  where: { id: d.where.id, title: d.where.title },
                  match: d.match ? { id: d.match.id, title: d.match.title } : null,
                }))}
                explored={canSend && !busy && !resurfaceMuted ? resurfaced : []}
                canSend={canSend}
                onOpen={(convId, branchId) =>
                  nav(`/w/${wid}?conv=${convId}` + (branchId ? `&branch=${branchId}` : ""))}
                onLinkFor={doLinkFor}
                onMute={() => setResurfaceMuted(true)}
                whoOf={(h) =>
                  h.role === "assistant" ? "Helix"
                    : h.author_id === user?.id ? "you"
                    : (emailOf(h.author_id) ?? "a teammate")}
              />
              {approval && (
                <div className={s.approveBar}>
                  <span style={{ fontSize: 15, color: "var(--gilt)" }} aria-hidden>{STATE.waiting}</span>
                  <span style={{ minWidth: 0 }}>
                    Helix wants to run{" "}
                    {approval.calls.length === 0 ? <strong>a sensitive tool</strong> : approval.calls.map((c, i) => (
                      <span key={c.id}>
                        {i > 0 && ", "}
                        <strong className="mono" style={{ fontSize: 12 }}>{c.name}</strong>
                        {c.args && <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>({c.args})</span>}
                      </span>
                    ))}
                    {" "}— this call leaves the workspace, so it needs your approval.
                  </span>
                  <div style={{ flex: 1 }} />
                  <Button variant="primary" onClick={() => decideApproval(true)}>Approve</Button>
                  <Button variant="ghost" onClick={() => decideApproval(false)}>Deny</Button>
                </div>
              )}
              {/* Went to TEAM, and said SETUP. The provider moved to workspace
                  settings when the Team page was split, and this banner — the
                  one thing a workspace with no key can click — kept pointing at
                  the page it had left. No glyph either: the sentence is the
                  whole message, and the mark that used to sit here was ⚿, which
                  renders as an empty box on plenty of machines. */}
              {canSend && providerUnconfigured && (
                <div className={s.remoteBanner} style={{ cursor: "pointer" }}
                  {...activatable(() => nav(`/w/${wid}/settings`))}>
                  This workspace has no LLM key yet — replies can't stream until one is added.
                  {" "}<u>Add a key under SETUP → Provider</u> (owners only).
                </div>
              )}
              {/* With the monitor folded away, a live run still has to be
                  visible and stoppable from the stage. */}
              {runLive && (
                <div className={s.runStrip}>
                  <span className={s.runStripDot} />
                  <span style={{ flex: 1, minWidth: 0 }}>
                    deep run · depth {monitor.run?.depth ?? 0}
                    {monitor.run?.status === "waiting" ? " · holding for you" : ""}
                  </span>
                  <button className={s.drawerBtn} style={{ minHeight: 32 }}
                    onClick={() => setDrawer("monitor")}>watch</button>
                  <button className={s.runStripKill} onClick={stopRun}>◼ Stop run</button>
                </div>
              )}
              {canSend ? (
                <Composer provider={provider} busy={busy} wid={wid} onSend={onSend} onDeep={onDeep}
                  onAgent={onAgent} onNote={doNote} agentHint={agentHint}
                  onLibrary={() => nav(`/w/${wid}/library`)}
                  onDraftChange={onDraftChange}
                  draft={composerDraft} onDraftConsumed={() => setComposerDraft(null)} />
              ) : (
                <>
                  {/* An Observer is not mute. They cannot address the model —
                      no sending, forking, escalating or steering — but they can
                      address the people, because the person you invite to
                      observe is usually the reviewer or supervisor who most
                      needs to say "that citation is wrong". */}
                  <div className={s.readonly}>
                    <span style={{ fontSize: 16 }} aria-hidden>{STATE.watching}</span>
                    <span style={{ fontSize: 13 }}>
                      You are an <strong style={{ color: "var(--ink-2)" }}>Observer</strong> — you
                      may watch live conversations and runs, and leave notes for the team,
                      but cannot send to Helix, fork, or steer.
                    </span>
                  </div>
                  {canNote && (
                    <Composer provider={provider} busy={busy} wid={wid} noteOnly
                      onSend={onSend} onDeep={onDeep} onAgent={onAgent} onNote={doNote}
                      onLibrary={() => nav(`/w/${wid}/library`)}
                      onDraftChange={onDraftChange}
                      draft={composerDraft} onDraftConsumed={() => setComposerDraft(null)} />
                  )}
                </>
              )}
            </div>
          </>
        )}
      </div>

      {/* RIGHT: monitor */}
      <DeepReasoningMonitor conversationId={activeConvId} id="chat-monitor"
        collapsed={!monitorOpen} onToggle={() => setMonitorOpen((v) => !v)} />

      {/* dismisses whichever drawer is open; inert above 1100px, where the CSS
          keeps it display:none and both panes are in the grid */}
      {drawer && (
        <button className={s.drawerScrim} aria-label="Close panel" onClick={() => setDrawer(null)} />
      )}

      {forkDlg && (
        <ForkDialog onClose={() => setForkDlg(null)}
          onConfirm={(name, intent) => { doFork(forkDlg.nodeId, name, intent); setForkDlg(null); }} />
      )}
      {concludeDlg && activeConv && (
        <ConcludeDialog conv={activeConv} onClose={() => setConcludeDlg(false)}
          onSave={(t) => { doConclude(t); setConcludeDlg(false); }} />
      )}
      {resolveDlg && (
        <ResolveDialog branch={resolveDlg}
          siblings={branches.filter((b) => b.id !== resolveDlg.id)}
          onClose={() => setResolveDlg(null)}
          onConfirm={(status, resolution) => { doResolve(resolveDlg.id, status, resolution); setResolveDlg(null); }} />
      )}
      {linkDlg && activeConv && (
        <LinkContextDialog
          candidates={conversations.filter(
            (c) => c.id !== activeConv.id && c.visibility === "shared" && !references.some((r) => r.id === c.id),
          )}
          onClose={() => setLinkDlg(false)}
          onPick={(id) => { doAddRef(id); setLinkDlg(false); }}
        />
      )}
      {renameDlg && (
        <Dialog title={`Rename ${renameDlg.kind}`} onClose={() => setRenameDlg(null)}
          footer={<>
            <Button variant="ghost" onClick={() => setRenameDlg(null)}>Cancel</Button>
            <Button variant="primary" onClick={doRename}>Rename</Button>
          </>}>
          <Input autoFocus value={renameDlg.name}
            onChange={(e) => setRenameDlg({ ...renameDlg, name: e.target.value })}
            onKeyDown={(e) => e.key === "Enter" && doRename()} />
        </Dialog>
      )}
      {deleteDlg && (
        <Dialog title={`Delete ${deleteDlg.kind} "${deleteDlg.name}"?`} onClose={() => setDeleteDlg(null)}
          footer={<>
            <Button variant="ghost" onClick={() => setDeleteDlg(null)}>Cancel</Button>
            <Button variant="oxblood" onClick={doDelete}>Delete forever</Button>
          </>}>
          <div style={{ fontSize: 13, color: "var(--ink-2)" }}>
            {deleteDlg.kind === "conversation"
              ? "Every branch, message and run record in this conversation is removed for the whole workspace — there is no undo."
              : "The branch and its own messages are removed (inherited context belongs to its ancestors and stays). Refused if anything has forked from it."}
          </div>
        </Dialog>
      )}
      {newDlg && (
        <Dialog title="New conversation" onClose={() => setNewDlg(false)}
          footer={<>
            <Button variant="ghost" onClick={() => setNewDlg(false)}>Cancel</Button>
            <Button variant="primary" onClick={() => { doNewConversation(draftTitle.trim(), draftVis); setNewDlg(false); }}>Create</Button>
          </>}>
          <Input autoFocus placeholder="Title (e.g. Retrieval chunking strategy)" value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { doNewConversation(draftTitle.trim(), draftVis); setNewDlg(false); } }} />
          <div style={{ display: "flex", gap: 8 }}>
            {(["shared", "private"] as const).map((v) => (
              <button key={v} onClick={() => setDraftVis(v)}
                style={{
                  flex: 1, padding: "8px 10px", borderRadius: 8, fontSize: 13,
                  border: `1px solid ${draftVis === v ? "var(--oxblood)" : "var(--rule-soft)"}`,
                  background: draftVis === v ? "var(--paper-3)" : "transparent",
                  color: draftVis === v ? "var(--oxblood)" : "var(--ink-3)",
                }}>
                {v === "shared" ? "Shared — whole workspace" : "Private — only you"}
              </button>
            ))}
          </div>
        </Dialog>
      )}
    </div>
  );
}

// The intent is the field this dialog should always have had. It used to ask
// only for a name, which is why every branch in every demo was called
// "experiment" — there was nothing meaningful to write, because the model held
// no notion of what the branch was for. A verdict recorded later ("we adopted
// experiment") says nothing; "we adopted 'chunk at 500 with overlap'" is a
// decision. The name stays, shortened to a label for the lineage.

