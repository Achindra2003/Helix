// The agent turn (FR-14) as its own controller.
//
// It is the most stateful thing the chat surface does: the stream arrives in
// SEGMENTS, because a sensitive tool call ends one segment on waiting() and the
// approval verdict opens the next, with the half-built message carried across
// the gap in a ref. That is a lot of machinery to have sitting in the middle of
// a view that also owns conversations, branches, history, drawers and replay —
// it is exactly the part nobody wants to read past.
//
// The view keeps ownership of the message list and the busy flag; this hook
// only borrows them, which is why they arrive as callbacks rather than the hook
// holding its own copy. Two sources of truth for "what is on screen" would be
// worse than a long file.
import { useRef, useState } from "react";
import { streamSSE } from "@/lib/sse";
import type { RunEvent } from "@/lib/types";
import type { ChatMessage, ToolActivity } from "@/components/chat/MessageList";

/** One line of "what the model asked the tool for" — enough to judge a call. */
export function compactArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([k, v]) => `${k}: ${typeof v === "string" ? `"${v}"` : JSON.stringify(v)}`)
    .join(", ")
    .slice(0, 140);
}

export function useAgentRun({
  setMessages, scrollDown, setBusy, onSettled, groundingByNode, toolsByNode,
}: {
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  scrollDown: () => void;
  setBusy: (b: boolean) => void;
  /** Refresh branch heads + conversation meta once a turn finishes. */
  onSettled: () => void;
  groundingByNode: Record<string, any[]>;
  toolsByNode: Record<string, ToolActivity[]>;
}) {
  // The in-flight agent turn: its stream comes in segments (each approval
  // pause ends one, each verdict opens the next), so the accumulating message
  // state lives in a ref that every segment's handler shares.
  const agentRunRef = useRef<{
    runId: string; userMsg: ChatMessage; asst: ChatMessage; acc: string;
    branchId: string; paused: boolean;
  } | null>(null);
  // A sensitive tool call holding for a human verdict (the banner + buttons).
  const [approval, setApproval] = useState<{ runId: string; calls: ToolActivity[] } | null>(null);

  // --- Agent turns (FR-14): chat with hands. Same bubble, plus a tool
  // ledger; a sensitive call ends the stream segment on waiting(approval)
  // and the verdict endpoint streams the continuation.
  function handleAgentEvent(ev: RunEvent) {
    const run = agentRunRef.current;
    if (!run) return;
    if (ev.kind === "agent_run") {
      run.runId = ev.run_id;
    } else if (ev.kind === "user_node") {
      run.userMsg.id = ev.node.id;
      run.userMsg.body = ev.node.content;
      setMessages((m) => [...m]);
    } else if (ev.kind === "grounding") {
      run.asst.grounding = ev.items;
      setMessages((m) => [...m]);
    } else if (ev.kind === "token") {
      run.acc += ev.text;
      run.asst.body = run.acc;
      setMessages((m) => [...m]);
      scrollDown();
    } else if (ev.kind === "tool_call") {
      (run.asst.tools ??= []).push({
        id: ev.id, name: ev.name, args: compactArgs(ev.arguments),
        sensitive: ev.sensitive, status: ev.sensitive ? "pending" : "running",
      });
      setMessages((m) => [...m]);
      scrollDown();
    } else if (ev.kind === "tool_result") {
      const t = run.asst.tools?.find((x) => x.id === ev.id && (x.status === "running" || x.status === "pending"));
      if (t) {
        t.status = ev.status;
        t.preview = ev.content;
        setMessages((m) => [...m]);
      }
    } else if (ev.kind === "waiting") {
      run.paused = true;
      setApproval({ runId: run.runId, calls: (run.asst.tools ?? []).filter((t) => t.status === "pending") });
    } else if (ev.kind === "complete") {
      if (ev.status === "error" && !run.acc) {
        run.asst.body = `[${ev.stop_reason}]`;
        setMessages((m) => [...m]);
      }
    } else if (ev.kind === "assistant_node") {
      run.asst.id = ev.node.id;
      run.asst.typing = false;
      run.asst.tokens = ev.node.token_count ? `${ev.node.token_count} tokens · ⚒ agent` : undefined;
      if (run.asst.grounding) groundingByNode[ev.node.id] = run.asst.grounding;
      if (run.asst.tools?.length) toolsByNode[ev.node.id] = run.asst.tools;
      setMessages((m) => [...m]);
    }
  }

  /** Await one SSE segment of an agent run. Paused-for-approval keeps the
   *  composer busy (the banner owns the next step); anything else finishes
   *  the turn. */
  async function finishAgentSegment(done: Promise<void>) {
    const run = agentRunRef.current;
    try {
      await done;
    } catch (e: any) {
      if (run) {
        run.asst.body = run.acc + (run.acc ? "\n" : "") + `[stream error: ${e?.message ?? e}]`;
        run.paused = false;
      }
    }
    if (agentRunRef.current?.paused) return;
    if (run) {
      run.asst.typing = false;
      setMessages((m) => [...m]);
    }
    agentRunRef.current = null;
    setApproval(null);
    setBusy(false);
    onSettled();
  }

  /** Start an agent turn on `branchId`. The caller owns "which branch" —
   *  creating one on demand is the view's job, not this controller's. */
  async function runAgent(text: string, branchId: string, authorColor: string, time: string) {
    setBusy(true);
    const userMsg: ChatMessage = {
      id: "tmp-u", role: "user", authorName: "You",
      authorColor, body: text, time,
    };
    const asst: ChatMessage = {
      id: "tmp-agent", role: "assistant", authorName: "Helix",
      body: "", time, typing: true, tools: [],
    };
    setMessages((m) => [...m, userMsg, asst]);
    scrollDown();
    agentRunRef.current = { runId: "", userMsg, asst, acc: "", branchId, paused: false };
    const h = streamSSE(`/conversations/${branchId}/agent`, { prompt: text }, handleAgentEvent);
    await finishAgentSegment(h.done);
  }

  async function decideApproval(approved: boolean) {
    const run = agentRunRef.current;
    if (!run?.runId) return;
    setApproval(null);
    run.paused = false;
    if (approved) {
      // Denials resolve via the gate's tool_result frames; approvals start
      // executing now — say so.
      for (const t of run.asst.tools ?? []) if (t.status === "pending") t.status = "running";
      setMessages((m) => [...m]);
    }
    const h = streamSSE(`/conversations/agent/runs/${run.runId}/approve`, { approved }, handleAgentEvent);
    await finishAgentSegment(h.done);
  }

  return { approval, runAgent, decideApproval, handleAgentEvent };
}
