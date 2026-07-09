import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listConversations, createConversation, listBranches, getHistory, forkBranch, getHealth, downloadExport,
  listReferences, addReference, removeReference, listMembers, getProviderSettings, getDeepRunStatus,
} from "@/lib/api";
import { streamSSE, attachSSE } from "@/lib/sse";
import { onRoomEvent, sendViewing } from "@/lib/realtime";
import type { Branch, Conversation, ConversationRef, GroundingItem, Node } from "@/lib/types";
import { useSession, useEffectiveRole } from "@/store/session";
import { useMonitor } from "@/store/monitor";
import { usePendingInsert } from "@/store/insert";
import { usePresenceStore } from "@/store/presence";
import { can } from "@/lib/rbac";
import { colorFor, nowTime } from "@/lib/format";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Dialog } from "@/components/common/Dialog";
import { Input } from "@/components/common/Input";
import { EmptyState } from "@/components/common/Feedback";
import { Frontispiece } from "@/components/brand/Frontispiece";
import { ConversationList } from "@/components/chat/ConversationList";
import { BranchTree } from "@/components/chat/BranchTree";
import { MessageList, type ChatMessage } from "@/components/chat/MessageList";
import { Composer } from "@/components/chat/Composer";
import { DeepReasoningMonitor } from "@/components/monitor/DeepReasoningMonitor";
import { ReplayBar } from "@/components/chat/ReplayBar";
import s from "@/components/chat/chat.module.css";

// Deep runs execute server-side and outlive the tab: remember the in-flight
// run so a reload can reattach to its stream instead of showing a dead monitor.
const deepKey = (wid: string) => `helix:deeprun:${wid}`;
interface SavedDeepRun {
  runId: string; conversationId: string; branchId: string; question: string; guided: boolean;
}

// Grounding citations live only in the stream (nodes don't persist them), but
// history reloads happen after every turn — remember which sources each
// assistant node cited so the chips survive the round-trip for this session.
const groundingByNode: Record<string, GroundingItem[]> = {};

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
    tokens: n.token_count ? `${n.token_count} tokens` : undefined,
    forkPoint: !!forkNodeId && n.id === forkNodeId,
    forkChildren: forkMap?.[n.id],
    grounding: groundingByNode[n.id],
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
  const [linkDlg, setLinkDlg] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  // Which branch is on screen *now* — deep runs finish asynchronously (maybe
  // after a branch switch or a reload), so history refreshes check this first.
  const activeBranchRef = useRef<string | null>(null);
  useEffect(() => { activeBranchRef.current = activeBranchId; }, [activeBranchId]);

  // Deep link from the Map: /w/:wid?conv=…&branch=… lands directly in that
  // thread at that branch. Consumed once, then removed from the URL.
  const [searchParams, setSearchParams] = useSearchParams();
  const wantedBranchRef = useRef<string | null>(searchParams.get("branch"));
  useEffect(() => {
    const conv = searchParams.get("conv");
    if (conv) {
      setActiveConvId(conv);
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      setBranches([{ id: r.branch_id, conversation_id: r.conversation_id, name: "main", parent_branch_id: null, fork_node_id: null, head_node_id: null }]);
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
    setBranches([{ id: r.branch_id, conversation_id: r.conversation_id, name: "main", parent_branch_id: null, fork_node_id: null, head_node_id: null }]);
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
          asstMsg.tokens = ev.node.token_count ? `${ev.node.token_count} tokens · ☁ ${provider}` : undefined;
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

  async function doFork(nodeId: string, name: string) {
    if (!activeConvId) return;
    try {
      const r = await forkBranch(activeConvId, nodeId, name || "experiment");
      const tree = await listBranches(activeConvId);
      setBranches(tree.items);
      setActiveBranchId(r.branch_id);
      push(`Forked → ${r.name}`);
    } catch (e: any) { push(e?.message ?? "Fork failed", "error"); }
  }

  function handleDeepEvent(ev: import("@/lib/types").RunEvent) {
    const run = useMonitor.getState().run;
    if (!run) return;
    if (ev.kind === "deep_run") {
      monitor.patch({ runId: ev.run_id });
      if (wid) {
        const saved: SavedDeepRun = {
          runId: ev.run_id, conversationId: run.conversationId ?? "", branchId: run.branchId ?? "",
          question: run.question, guided: !!run.onSteer,
        };
        sessionStorage.setItem(deepKey(wid), JSON.stringify(saved));
      }
    } else if (ev.kind === "queued") {
      // Waiting behind the workspace's concurrency cap — say so instead of stalling.
      monitor.patch({ status: "queued", queuePosition: ev.position });
    } else if (ev.kind === "step") {
      const p = ev.payload ?? {};
      const num = (k: string, d: number) => (typeof p[k] === "number" ? (p[k] as number) : d);
      // Convergence viz: collect each cycle's stability reading (and the run's
      // resolved halting threshold) for the sparkline + closing ring.
      const stabNow = typeof p.stability === "number" ? (p.stability as number) : null;
      const thr = typeof p.stability_threshold === "number" ? (p.stability_threshold as number) : undefined;
      monitor.patch({
        depth: ev.depth ?? run.depth,
        energy: ev.energy ?? run.energy,
        loopGuard: num("loop_guard", run.loopGuard),
        stability: num("stability", run.stability),
        confidence: num("confidence", run.confidence),
        ...(stabNow !== null && stabNow !== run.stabilityHistory[run.stabilityHistory.length - 1]
          ? { stabilityHistory: [...run.stabilityHistory, stabNow] } : {}),
        ...(thr !== undefined ? { threshold: thr } : {}),
        // A queued run has started; a replayed pause has been steered past.
        ...(run.status === "queued" || run.status === "waiting" ? { status: "live" as const } : {}),
      });
      const stab = typeof p.stability === "number" ? ` · stab ${(p.stability as number).toFixed(2)}` : "";
      monitor.addStep({ kind: ev.node, meta: `step ${ev.idx} · depth ${ev.depth}${stab}`, text: pickText(p) });
    } else if (ev.kind === "budget") {
      monitor.patch({ budgetPct: Math.round(ev.pct <= 1 ? ev.pct * 100 : ev.pct), tokensUsed: ev.tokens_used ?? run.tokensUsed });
    } else if (ev.kind === "token") {
      monitor.patch({ answer: ((useMonitor.getState().run?.answer ?? "") + ev.text).replace(/^\s*\[answer\]\s*/i, "") });
    } else if (ev.kind === "waiting") {
      monitor.addStep({ kind: "steer", meta: "paused for guidance", text: "The loop is holding — steer it, or let it continue." });
      monitor.patch({ status: "waiting" });
    } else if (ev.kind === "complete") {
      monitor.patch({ status: ev.status === "killed" ? "killed" : ev.status === "error" ? "error" : "done", stopReason: ev.stop_reason });
      if (wid) sessionStorage.removeItem(deepKey(wid));
    } else if (ev.kind === "assistant_node") {
      const cur = useMonitor.getState().run;
      if (cur && !cur.answer && ev.node.content) monitor.patch({ answer: ev.node.content });
    }
  }

  /** Await one SSE segment of a deep run; a guided run has several (each pause
   *  ends the stream, each steer opens the next). History refreshes only when
   *  the run truly finishes — a paused run has no assistant reply yet. */
  async function finishDeepSegment(done: Promise<void>, branchId: string) {
    try {
      await done;
      const cur = useMonitor.getState().run;
      if (cur && cur.status === "live") monitor.patch({ status: "done", stopReason: cur.stopReason || "ended" });
    } catch (e: any) {
      const cur = useMonitor.getState().run;
      if (cur) monitor.patch({ status: e?.name === "AbortError" ? "killed" : "error", stopReason: e?.name === "AbortError" ? "killed by operator" : (e?.message ?? "error") });
    }
    const status = useMonitor.getState().run?.status;
    if (status !== "waiting" && status !== "live" && status !== "queued" && wid) {
      // Terminal on this client — a reload should not reattach to it.
      sessionStorage.removeItem(deepKey(wid));
    }
    if (status !== "waiting" && activeBranchRef.current === branchId) {
      getHistory(branchId).then((r) => setMessages(r.nodes.map((n) => nodeToMsg(n, user?.id, activeBranch?.fork_node_id ?? null, emailOf, forkSourceMap)))).catch(() => {});
    }
  }

  async function steerRun(guidance: string) {
    const cur = useMonitor.getState().run;
    if (!cur?.runId || !cur.branchId || cur.status !== "waiting") return;
    monitor.patch({ status: "live" });
    monitor.addStep({ kind: "steer", meta: "human guidance", text: guidance || "(continue unchanged)" });
    const h = streamSSE(`/conversations/deep/runs/${cur.runId}/steer`, { guidance }, handleDeepEvent);
    monitor.patch({ abort: h.abort });
    await finishDeepSegment(h.done, cur.branchId);
  }

  async function onDeep(text: string, guided: boolean) {
    const branchId = await ensureConversation();
    if (!branchId || !activeConvId) return;
    const h = streamSSE(`/conversations/${branchId}/deep`, { prompt: text, steerable: guided }, handleDeepEvent);
    monitor.start({
      status: "live", question: text, depth: 0, energy: 0, loopGuard: 0, stability: 0, confidence: 0,
      stabilityHistory: [],
      budgetPct: 0, tokensUsed: 0, steps: [], answer: "", stopReason: "",
      abort: h.abort, conversationId: activeConvId, branchId,
      canControl: can(role, "run.control"),
      onSteer: guided ? (g) => { steerRun(g); } : undefined,
    });
    await finishDeepSegment(h.done, branchId);
  }

  // Reconnect-on-load (AI-LANE-CONTRACTS §2.2): if this workspace has an
  // in-flight deep run from a previous page load, reattach to its stream —
  // replaying the event log from 0 rebuilds the whole monitor (gauges, trace,
  // sparkline), then follows live. A finished/expired run just clears itself.
  useEffect(() => {
    if (!wid) return;
    const raw = sessionStorage.getItem(deepKey(wid));
    if (!raw) return;
    let saved: SavedDeepRun;
    try { saved = JSON.parse(raw); } catch { sessionStorage.removeItem(deepKey(wid)); return; }
    if (!saved?.runId) { sessionStorage.removeItem(deepKey(wid)); return; }
    (async () => {
      try {
        const st = await getDeepRunStatus(saved.runId);
        if (st.status === "done" || st.status === "error" || st.status === "killed") {
          sessionStorage.removeItem(deepKey(wid));
          return;
        }
        monitor.start({
          status: st.status === "queued" ? "queued" : "live",
          question: saved.question, depth: 0, energy: 0, loopGuard: 0, stability: 0, confidence: 0,
          stabilityHistory: [], budgetPct: 0, tokensUsed: 0, steps: [], answer: "", stopReason: "",
          conversationId: saved.conversationId, branchId: saved.branchId, runId: saved.runId,
          queuePosition: st.queue_position ?? undefined,
          canControl: can(role, "run.control"),
          onSteer: saved.guided ? (g) => { steerRun(g); } : undefined,
        });
        const h = attachSSE(`/conversations/deep/runs/${saved.runId}/stream?after=0`, handleDeepEvent);
        monitor.patch({ abort: h.abort });
        await finishDeepSegment(h.done, saved.branchId);
      } catch {
        // 404: the run finished and its live handle expired — the assistant
        // node is already in history, nothing to reattach to.
        sessionStorage.removeItem(deepKey(wid));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wid]);

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
      if (ev.kind === "conversation.created") {
        qc.invalidateQueries({ queryKey: ["conversations", wid] });
      } else if (ev.kind === "branch.created") {
        if (ev.conversation_id === activeConvId) {
          listBranches(activeConvId).then((r) => setBranches(r.items)).catch(() => {});
        }
      } else if (ev.kind === "references.updated") {
        if (ev.conversation_id === activeConvId) {
          qc.invalidateQueries({ queryKey: ["references", activeConvId] });
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
        } else if (e.kind === "step" && run) {
          // A teammate escalated to Deep Reason on this branch: if my monitor
          // is idle, watch their reasoning trace live (no kill control — it's
          // their run).
          const cur = useMonitor.getState().run;
          if (!run.watching && (!cur || cur.status !== "live")) {
            run.watching = true;
            monitor.start({
              status: "live", question: `👁 watching ${ev.author_id}'s deep run`,
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
          run.asst.tokens = e.node.token_count ? `${e.node.token_count} tokens · ☁ ${provider}` : undefined;
          if (run.asst.grounding) groundingByNode[e.node.id] = run.asst.grounding;
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

  return (
    <div className={`${s.grid} folio`}>
      {/* LEFT */}
      <div className={s.left}>
        <div className={s.scrollList}>
          <ConversationList
            conversations={conversations}
            activeId={activeConvId}
            canCreate={canSend}
            onSelect={setActiveConvId}
            onNew={() => { setDraftTitle(""); setNewDlg(true); }}
            viewers={conversationViewers}
          />
          {activeConv && branches.length > 0 && (
            <BranchTree branches={branches} activeId={activeBranchId} onSelect={setActiveBranchId} />
          )}
        </div>
        <div className={s.leftFoot}><span className={s.liveDot} /> live · server-ordered log</div>
      </div>

      {/* STAGE */}
      <div className={s.stage}>
        <div className={s.stageGeo}><Frontispiece size={560} animate={false} /></div>
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
            <div className={s.stageHead}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className={s.stageTitle}>{activeConv.title}</div>
                <div className={s.stageMeta}>
                  <span className={s.chip} style={{ color: activeConv.visibility === "private" ? "var(--ink-3)" : "var(--oxblood)" }}>
                    {activeConv.visibility === "private" ? "◍ private" : "⊙ shared"}
                  </span>
                  <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>
                    on <span style={{ color: "var(--oxblood)" }}>{activeBranch?.name ?? "main"}</span>
                  </span>
                  <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{messages.length} nodes</span>
                </div>
                {(references.length > 0 || canSend) && (
                  <div className={s.stageMeta} style={{ marginTop: 6, flexWrap: "wrap" }}>
                    <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-3)" }}>linked context:</span>
                    {references.length === 0 && (
                      <span style={{ fontSize: 12.5, color: "var(--ink-3)", fontStyle: "italic" }}>none</span>
                    )}
                    {references.map((r) => (
                      <span key={r.id} className={s.chip} title="Replies here draw on this thread's live context"
                        style={{ color: "var(--ink-2)", display: "inline-flex", alignItems: "center", gap: 6 }}>
                        ⛓ {r.title}
                        {canSend && (
                          <button onClick={() => doRemoveRef(r.id)} title="Unlink"
                            style={{ border: 0, background: "transparent", cursor: "pointer", color: "var(--ink-3)", fontSize: 13, lineHeight: 1, padding: 0 }}>×</button>
                        )}
                      </span>
                    ))}
                    {canSend && (
                      <button onClick={() => setLinkDlg(true)} className={s.chip}
                        title="Pull another shared thread's context into this conversation"
                        style={{ cursor: "pointer", border: "1px dashed var(--rule-soft)", background: "transparent", color: "var(--oxblood)" }}>
                        ＋ link context
                      </button>
                    )}
                  </div>
                )}
              </div>
              {messages.length > 0 && (
                <>
                  <ReplayBar total={messages.length} value={replay} onChange={setReplay} />
                  <button className={s.chip} onClick={() => downloadExport(activeConv.id, activeBranchId!, "md").catch(() => push("Export failed", "error"))} title="Export Markdown" style={{ cursor: "pointer", border: "none", background: "transparent", color: "var(--ink-2)" }}>↓ md</button>
                  <button className={s.chip} onClick={() => downloadExport(activeConv.id, activeBranchId!, "json").catch(() => push("Export failed", "error"))} title="Export JSON" style={{ cursor: "pointer", border: "none", background: "transparent", color: "var(--ink-2)" }}>↓ json</button>
                </>
              )}
              {canFork && (
                <Button onClick={() => activeBranch?.head_node_id ? setForkDlg({ nodeId: activeBranch.head_node_id }) : push("Send a message before forking", "error")}>
                  <span style={{ color: "var(--oxblood)" }}>⌇</span> Fork
                </Button>
              )}
            </div>

            <div className={s.canvas} ref={canvasRef}>
              {shownMessages.length === 0 ? (
                <EmptyState title="A blank page">
                  {canSend ? "Send the first message — the whole team shares this thread, and any reply can be forked into its own branch."
                           : "This thread is empty."}
                </EmptyState>
              ) : (
                <MessageList messages={shownMessages} onForkHere={canFork ? (id) => setForkDlg({ nodeId: id }) : undefined} />
              )}
            </div>

            <div className={s.composerWrap}>
              {remoteAuthorId && (
                <div className={s.remoteBanner}>
                  <span
                    className={s.rowDot}
                    style={{ background: colorFor(emailOf(remoteAuthorId) ?? remoteAuthorId) }}
                  />
                  ✒ {emailOf(remoteAuthorId) ?? "a teammate"} is asking Helix…
                </div>
              )}
              {canSend && providerUnconfigured && (
                <div className={s.remoteBanner} style={{ cursor: "pointer" }} onClick={() => nav(`/w/${wid}/members`)}>
                  ⚿ This workspace has no LLM key yet — replies can't stream until one is added.
                  {" "}<u>Add a key under TEAM → Provider</u> (owners only).
                </div>
              )}
              {canSend ? (
                <Composer provider={provider} busy={busy} onSend={onSend} onDeep={onDeep} onLibrary={() => nav(`/w/${wid}/library`)} />
              ) : (
                <div className={s.readonly}>
                  <span style={{ fontSize: 16 }}>◉</span>
                  <span style={{ fontSize: 13.5 }}>You are an <strong style={{ color: "var(--ink-2)" }}>Observer</strong> — read-only. You may watch live conversations and runs, but cannot send, fork, or steer.</span>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* RIGHT: monitor */}
      <DeepReasoningMonitor conversationId={activeConvId} />

      {forkDlg && (
        <ForkDialog onClose={() => setForkDlg(null)} onConfirm={(name) => { doFork(forkDlg.nodeId, name); setForkDlg(null); }} />
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
                {v === "shared" ? "⊙ Shared — whole workspace" : "◍ Private — only you"}
              </button>
            ))}
          </div>
        </Dialog>
      )}
    </div>
  );
}

function ForkDialog({ onClose, onConfirm }: { onClose: () => void; onConfirm: (name: string) => void }) {
  const [name, setName] = useState("experiment");
  return (
    <Dialog title="Fork a new branch" onClose={onClose}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={() => onConfirm(name.trim())}>Fork</Button>
      </>}>
      <div style={{ fontSize: 13, color: "var(--ink-3)" }}>
        The new branch inherits the shared context up to this point, then diverges on its own.
      </div>
      <Input autoFocus value={name} onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") onConfirm(name.trim()); }} />
    </Dialog>
  );
}

function LinkContextDialog(
  { candidates, onClose, onPick }: { candidates: Conversation[]; onClose: () => void; onPick: (id: string) => void },
) {
  return (
    <Dialog title="Link context from another thread" onClose={onClose}
      footer={<Button variant="ghost" onClick={onClose}>Done</Button>}>
      <div style={{ fontSize: 13, color: "var(--ink-3)", marginBottom: 4 }}>
        Pick a shared conversation. Its <strong>live</strong> context is folded into this thread's
        replies — and stays in sync as that thread grows. This is a reference, not a fork: nothing is copied.
      </div>
      {candidates.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--ink-3)", fontStyle: "italic" }}>
          No other shared threads in this workspace to link yet.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 280, overflowY: "auto" }}>
          {candidates.map((c) => (
            <button key={c.id} onClick={() => onPick(c.id)}
              style={{
                textAlign: "left", padding: "9px 11px", borderRadius: 8, cursor: "pointer",
                border: "1px solid var(--rule-soft)", background: "transparent", color: "var(--ink-2)", fontSize: 13.5,
              }}>
              <span style={{ color: "var(--oxblood)" }}>⊙</span> {c.title}
            </button>
          ))}
        </div>
      )}
    </Dialog>
  );
}

function pickText(p: Record<string, unknown>): string {
  if (!p) return "";
  for (const k of ["thought", "synthesis", "surfaced_insight", "insight", "reflection", "seed"]) {
    const v = p[k];
    if (typeof v === "string" && v.trim()) return v;
  }
  const v = Object.values(p).find((x) => typeof x === "string" && (x as string).length > 4);
  return (v as string) ?? "";
}
