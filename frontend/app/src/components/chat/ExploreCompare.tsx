import { useEffect, useRef, useState } from "react";
import { getHistory, voteBranch } from "@/lib/api";
import { streamSSE } from "@/lib/sse";
import type { Branch } from "@/lib/types";
import { Button } from "@/components/common/Button";
import { Markdown } from "@/components/common/Markdown";
import s from "./chat.module.css";

/**
 * Several explorations, side by side.
 *
 * Helix's signature move is branching, and until now you could only read one
 * branch at a time — which is fine for "continue this exploration" and useless
 * for the question a brainstorm actually asks: *which of these is best?*
 * Answering that by clicking between four branches and holding them in your
 * head is the work the product was supposed to remove.
 *
 * So the columns are the comparison. Each one is a real branch — it keeps its
 * angle, its lineage, its verdict — and the controls under it are the ones that
 * already existed: back it, or open it and carry on. Nothing here is a new kind
 * of object; it is a different way of looking at the ones there are.
 */
export function ExploreCompare({
  branches, ask, meId, canWrite, onClose, onOpen, onResolve, onVoted,
}: {
  branches: Branch[];
  /** True for a fresh fan-out: send each branch its own angle as the message.
   *  There is no separate question to ask — a fork already inherits the thread
   *  up to its fork point, so the angle is the whole of what is new. False when
   *  comparing branches that already have answers. */
  ask: boolean;
  meId?: string;
  canWrite: boolean;
  onClose: () => void;
  onOpen: (branchId: string) => void;
  onResolve: (branch: Branch) => void;
  onVoted: (branchId: string, votes: string[]) => void;
}) {
  // Per branch: the reply text and whether it is still arriving.
  const [replies, setReplies] = useState<Record<string, { body: string; busy: boolean }>>(
    () => Object.fromEntries(branches.map((b) => [b.id, { body: "", busy: ask }])),
  );
  // The fan-out must fire exactly once. In StrictMode the effect runs twice,
  // and without this each column would be asked the question twice — two
  // charges on the workspace's key and two answers racing into one column.
  const fired = useRef(false);

  useEffect(() => {
    if (fired.current) return;
    fired.current = true;

    if (!ask) {
      // Comparing what is already there: the last assistant turn per branch.
      branches.forEach(async (b) => {
        try {
          const { nodes } = await getHistory(b.id);
          const last = [...nodes].reverse().find((n) => n.role === "assistant");
          setReplies((r) => ({ ...r, [b.id]: { body: last?.content ?? "", busy: false } }));
        } catch {
          setReplies((r) => ({ ...r, [b.id]: { body: "", busy: false } }));
        }
      });
      return;
    }

    // All at once, deliberately. Asking them in sequence would make the last
    // column wait for the first three, and the point of the view is that the
    // answers arrive together and can be read against each other.
    branches.forEach((b) => {
      let acc = "";
      const handle = streamSSE(`/conversations/${b.id}/messages`, { prompt: b.intent }, (ev) => {
        if (ev.kind === "token") {
          acc += ev.text;
          setReplies((r) => ({ ...r, [b.id]: { body: acc, busy: true } }));
        }
      });
      handle.done
        .catch((e: any) => { acc = acc || `Could not run this angle: ${e?.message ?? e}`; })
        .finally(() => setReplies((r) => ({ ...r, [b.id]: { body: acc, busy: false } })));
    });
  }, [branches, ask]);

  async function back(b: Branch) {
    try {
      const r = await voteBranch(b.id);
      onVoted(b.id, r.votes);
    } catch { /* the tally refetches with the tree */ }
  }

  const running = Object.values(replies).some((r) => r.busy);

  return (
    <div className={s.compareWrap} role="dialog" aria-label="Compare explorations">
      <div className={s.compareHead}>
        <div>
          <div className={s.compareTitle}>
            {ask ? "Exploring in parallel" : "Comparing explorations"}
          </div>
          <div className={s.compareSub}>
            {running
              ? "Answers are arriving. Back the ones worth keeping."
              : "Back the ones worth keeping, then adopt one with a reason."}
          </div>
        </div>
        <Button variant="ghost" onClick={onClose}>Done</Button>
      </div>

      <div className={s.compareCols}>
        {branches.map((b) => {
          const reply = replies[b.id] ?? { body: "", busy: false };
          const votes = b.votes ?? [];
          const backing = !!meId && votes.includes(meId);
          return (
            <section key={b.id} className={s.compareCol}>
              <header className={s.compareColHead}>
                {/* The angle, not the label. The label is a slug derived from
                    this sentence, and the sentence is what you are judging. */}
                <div className={s.compareAngle}>{b.intent || b.name}</div>
                <div className={`mono ${s.compareName}`}>{b.name}</div>
              </header>

              <div className={s.compareBody}>
                {reply.busy && !reply.body
                  ? <span className={s.compareWaiting}>thinking…</span>
                  : reply.body
                    ? <Markdown>{reply.body}</Markdown>
                    : <span className={s.compareWaiting}>no answer yet</span>}
              </div>

              <footer className={s.compareActs}>
                {canWrite && (
                  <button
                    className={`${s.branchVote} ${backing ? s.branchVoteOn : ""} ${s.branchVoteShown}`}
                    aria-pressed={backing}
                    title={backing ? "You're backing this — click to withdraw" : "Back this exploration"}
                    onClick={() => back(b)}
                  >
                    {backing ? "backing" : "back"}{votes.length ? ` · ${votes.length}` : ""}
                  </button>
                )}
                <div style={{ flex: 1 }} />
                {canWrite && (
                  <button className={s.compareLink} onClick={() => onResolve(b)}>
                    verdict
                  </button>
                )}
                <button className={s.compareLink} onClick={() => onOpen(b.id)}>
                  open ⟶
                </button>
              </footer>
            </section>
          );
        })}
      </div>
    </div>
  );
}
