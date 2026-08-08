// The dialogs the chat surface opens: forking an exploration, recording what
// came of it, concluding the thread, and linking another thread's context in.
//
// Lifted out of ChatView because they are pure presentational components that
// take props and hold their own draft state — they never needed to see the
// view's 40-odd pieces of state, and living in the same file only made that
// file harder to hold in your head.
import { useState } from "react";
import { streamSSE } from "@/lib/sse";
import type { Branch, BranchStatus, Conversation } from "@/lib/types";
import { Button } from "@/components/common/Button";
import { Dialog } from "@/components/common/Dialog";
import { Input, Field } from "@/components/common/Input";
import { ACTION, PLACE } from "@/lib/glyphs";
import s from "@/components/chat/chat.module.css";

export function ForkDialog({ onClose, onConfirm }: {
  onClose: () => void;
  onConfirm: (name: string, intent: string) => void;
}) {
  const [intent, setIntent] = useState("");
  const [name, setName] = useState("");
  // Fall back to a label derived from the intent, so nobody has to name a
  // thing twice to get on with the work.
  const label = name.trim() || intent.trim().split(/\s+/).slice(0, 3).join("-").toLowerCase() || "experiment";
  const go = () => onConfirm(label, intent.trim());
  return (
    <Dialog title="Fork a new branch" onClose={onClose}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={go}>Fork</Button>
      </>}>
      <div style={{ fontSize: 13, color: "var(--ink-3)" }}>
        The new branch inherits the shared context up to this point, then diverges on its own.
      </div>
      <Field label="What are you trying?">
        <Input autoFocus value={intent} onChange={(e) => setIntent(e.target.value)}
          placeholder="e.g. chunk at 500 chars with overlap"
          onKeyDown={(e) => { if (e.key === "Enter") go(); }} />
      </Field>
      <Field label={`Label — shown in the lineage (${label})`}>
        <Input value={name} onChange={(e) => setName(e.target.value)}
          placeholder="optional"
          onKeyDown={(e) => { if (e.key === "Enter") go(); }} />
      </Field>
    </Dialog>
  );
}

// The thread's own ending. Helix drafts, a human accepts — the two are
// separate on purpose: a draft nobody read is not a conclusion, and the whole
// point of the record is that someone stood behind it.
export function ConcludeDialog({ conv, onClose, onSave }: {
  conv: Conversation;
  onClose: () => void;
  onSave: (text: string) => void;
}) {
  const [text, setText] = useState(conv.conclusion ?? "");
  const [drafting, setDrafting] = useState(false);
  const [failed, setFailed] = useState("");

  function draft() {
    setDrafting(true);
    setFailed("");
    let acc = "";
    const h = streamSSE(`/conversations/${conv.id}/synthesize`, {}, (ev: any) => {
      if (ev.kind === "token") { acc += ev.text; setText(acc); }
      else if (ev.kind === "complete" && ev.status === "error") setFailed(ev.stop_reason ?? "draft failed");
    });
    h.done.catch((e: any) => setFailed(e?.message ?? "draft failed")).finally(() => setDrafting(false));
  }

  return (
    <Dialog title={`Conclude “${conv.title}”`} onClose={onClose}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button onClick={draft} disabled={drafting}>
          {drafting ? "Reading the branches…" : `${ACTION.verdict} Draft from the branches`}
        </Button>
        <Button variant="primary" onClick={() => onSave(text.trim())}>
          {text.trim() ? "Record it" : "Clear the conclusion"}
        </Button>
      </>}>
      <div style={{ fontSize: 13, color: "var(--ink-3)" }}>
        What does the team now believe? Helix can read the branches and draft
        this, but nothing is recorded until you accept it.
      </div>
      <textarea
        className={s.concludeBox}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="e.g. We chunk at 500 characters with overlap. Semantic chunking read better but lost cross-section context and cost 3x to ingest."
        rows={7}
        autoFocus
      />
      {failed && (
        <div style={{ fontSize: 12, color: "var(--oxblood)" }}>
          Could not draft: {failed}. Write it yourself — the record matters more
          than the draft.
        </div>
      )}
    </Dialog>
  );
}

// Recording what came of an exploration. The reason is required for a verdict
// and refused server-side if blank: "we chose this" without a why is exactly
// the thing this product exists to stop happening.
export function ResolveDialog({ branch, siblings = [], onClose, onConfirm }: {
  branch: Branch;
  // The other explorations under the same question, so the tally can be read
  // as a comparison. A count on its own ("3 backing") says nothing; "3 of 5,
  // against 1 elsewhere" is the thing a verdict is actually weighing.
  siblings?: Branch[];
  onClose: () => void;
  onConfirm: (status: BranchStatus, resolution: string) => void;
}) {
  const [status, setStatus] = useState<BranchStatus>(
    branch.status === "open" ? "adopted" : branch.status,
  );
  const [resolution, setResolution] = useState(branch.resolution);
  const needsReason = status !== "open";
  const ready = !needsReason || resolution.trim().length > 0;
  const CHOICES: { key: BranchStatus; label: string; hint: string }[] = [
    { key: "adopted", label: "Adopted", hint: "this is the way we went" },
    { key: "abandoned", label: "Abandoned", hint: "we tried it and it lost" },
    { key: "open", label: "Reopen", hint: "still live — clears the verdict" },
  ];
  return (
    <Dialog title={`What came of “${branch.name}”?`} onClose={onClose}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={!ready}
          onClick={() => onConfirm(status, resolution.trim())}>Record</Button>
      </>}>
      {branch.intent && (
        <div style={{ fontSize: 13, color: "var(--ink-3)" }}>
          It set out to: <span style={{ color: "var(--ink-2)" }}>{branch.intent}</span>
        </div>
      )}
      {/* The room's reading, shown while the verdict is being written — the
          point at which it is actually useful. Deliberately presented as
          evidence and never as a result: the Record button does not care what
          the tally says, because a decision the team can defend is one someone
          took responsibility for, not one a count made for them. */}
      {(branch.votes?.length || siblings.some((b) => b.votes?.length)) ? (
        <div style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: 1.5 }}>
          <span style={{ color: "var(--gilt-1)" }}>
            {branch.votes?.length ?? 0} backing this
          </span>
          {siblings.filter((b) => b.votes?.length).length > 0 && (
            <>
              {" · "}
              {siblings
                .filter((b) => b.votes?.length)
                .map((b) => `${b.votes.length} on “${b.name}”`)
                .join(" · ")}
            </>
          )}
          <div style={{ marginTop: 2 }}>A reading of the room, not the decision.</div>
        </div>
      ) : null}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {CHOICES.map((c) => (
          <label key={c.key} style={{ display: "flex", alignItems: "baseline", gap: 9, cursor: "pointer", fontSize: 14 }}>
            <input type="radio" name="verdict" checked={status === c.key}
              onChange={() => setStatus(c.key)} style={{ accentColor: "var(--oxblood)" }} />
            <span>{c.label}</span>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{c.hint}</span>
          </label>
        ))}
      </div>
      {needsReason && (
        <Field label="Why — this is what makes it defensible later">
          <Input autoFocus value={resolution} onChange={(e) => setResolution(e.target.value)}
            placeholder="e.g. better recall on long PDFs, same cost"
            onKeyDown={(e) => { if (e.key === "Enter" && ready) onConfirm(status, resolution.trim()); }} />
        </Field>
      )}
      <div style={{ fontSize: 12, color: "var(--ink-3)" }}>
        Nothing is deleted. An abandoned branch stays readable — it is half of why
        the adopted one holds up.
      </div>
    </Dialog>
  );
}

export function LinkContextDialog(
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
                border: "1px solid var(--rule-soft)", background: "transparent", color: "var(--ink-2)", fontSize: 13,
              }}>
              <span style={{ color: "var(--oxblood)" }} aria-hidden>{PLACE.chat}</span> {c.title}
            </button>
          ))}
        </div>
      )}
    </Dialog>
  );
}
