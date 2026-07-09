import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listPrompts, savePrompt } from "@/lib/api";
import { onRoomEvent } from "@/lib/realtime";
import { usePendingInsert } from "@/store/insert";
import { useSession, useEffectiveRole } from "@/store/session";
import { can } from "@/lib/rbac";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Dialog } from "@/components/common/Dialog";
import { Input } from "@/components/common/Input";
import { Spinner, EmptyState } from "@/components/common/Feedback";
import s from "./library.module.css";

// Neutral manuscript ornaments (fleurons), not esoteric sigils.
const ORNAMENTS = ["❧", "◆", "❖", "✿", "●", "◈"];

const STARTERS = [
  { title: "Socratic critique", body: "Interrogate the argument above. Surface its weakest assumption, then steelman the opposite view in three sentences.", tags: ["review", "reasoning"] },
  { title: "Extract action items", body: "From the thread above, list every commitment as: owner — action — due signal. Omit discussion.", tags: ["summarize", "team"] },
  { title: "Adversarial red-team", body: "You are a hostile reviewer. Find the three ways this design fails under load, bad input, or a malicious tenant.", tags: ["security", "reasoning"] },
  { title: "Tighten prose", body: "Rewrite the passage above 30% shorter with no loss of meaning. Prefer plain verbs.", tags: ["writing"] },
  { title: "Explain like a senior", body: "Explain the concept to a strong engineer new to the domain. One analogy, then the precise mechanism.", tags: ["teaching"] },
];

export function LibraryView() {
  const { wid } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { push } = useToast();
  const role = useEffectiveRole();
  const canWrite = can(role, "prompt.write");
  const request = usePendingInsert((st) => st.request);

  const [search, setSearch] = useState("");
  const [dlg, setDlg] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tags, setTags] = useState("");
  const [seeding, setSeeding] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["prompts", wid],
    queryFn: () => listPrompts(wid!),
    enabled: !!wid,
  });
  const prompts = data?.prompts ?? [];

  // Live fan-out: a teammate saving a prompt refreshes the library in place.
  useEffect(
    () =>
      onRoomEvent((ev) => {
        if (ev.kind === "prompt.saved") qc.invalidateQueries({ queryKey: ["prompts", wid] });
      }),
    [wid, qc],
  );

  // Seed a starter set the first time a workspace's library is empty (no LLM cost).
  useEffect(() => {
    if (!wid || isLoading || seeding || prompts.length > 0 || !canWrite) return;
    setSeeding(true);
    (async () => {
      for (const p of STARTERS) await savePrompt(wid, p.title, p.body, p.tags).catch(() => {});
      await qc.invalidateQueries({ queryKey: ["prompts", wid] });
      setSeeding(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wid, isLoading, prompts.length, canWrite]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return prompts.filter((p) =>
      !q || p.title.toLowerCase().includes(q) || p.body.toLowerCase().includes(q) ||
      (p.tags ?? []).some((t) => t.toLowerCase().includes(q)));
  }, [prompts, search]);

  async function doSave() {
    if (!wid || !title.trim() || !body.trim()) return;
    try {
      await savePrompt(wid, title.trim(), body.trim(), tags.split(",").map((t) => t.trim()).filter(Boolean));
      await qc.invalidateQueries({ queryKey: ["prompts", wid] });
      setDlg(false); setTitle(""); setBody(""); setTags("");
      push("Prompt saved");
    } catch (e: any) { push(e?.message ?? "Save failed", "error"); }
  }

  function insert(id: string) {
    request(id);
    nav(`/w/${wid}`);
    push("Inserting prompt into the conversation…");
  }

  return (
    <div className={`${s.scroll} folio`}>
      <div className={s.inner}>
        <div className={s.head}>
          <div style={{ flex: 1 }}>
            <div className="serif-d" style={{ fontSize: 32 }}>Prompt Library</div>
            <div style={{ color: "var(--ink-3)", marginTop: 8, fontSize: 13.5 }}>
              The shared record of what works — tagged, searchable, reusable across every conversation.
            </div>
          </div>
          {canWrite && <Button variant="primary" onClick={() => setDlg(true)}>+ Save prompt</Button>}
        </div>
        <div className="chapter-rule" aria-hidden>❦</div>

        <div className={s.search}>
          <span style={{ color: "var(--oxblood)", fontSize: 15 }}>⌕</span>
          <input className={s.searchInput} placeholder="Search title, body, or tags…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{filtered.length} prompts</span>
        </div>

        {isLoading || seeding ? <Spinner /> : filtered.length === 0 ? (
          <EmptyState title="An empty library">Save a winning prompt — a page kept here can be inserted into any thread, by anyone on the team.</EmptyState>
        ) : (
          <div className={s.grid}>
            {filtered.map((p, i) => (
              <div key={p.id} className={s.card} style={{ animationDelay: `${Math.min(i, 10) * 45}ms` }}>
                <div className={s.cardHead}>
                  <span className={s.sigil}>{ORNAMENTS[i % ORNAMENTS.length]}</span>
                  <div className={s.cardTitle}>{p.title}</div>
                </div>
                <div className={s.cardBody}>"{p.body}"</div>
                <div className={s.cardFoot}>
                  {(p.tags ?? []).map((t) => <span key={t} className={s.tag}>{t}</span>)}
                  <div style={{ flex: 1 }} />
                  {can(role, "message.send") && (
                    <Button onClick={() => insert(p.id)} style={{ padding: "4px 10px", fontSize: 12, color: "var(--oxblood)" }}>Insert →</Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {dlg && (
        <Dialog title="Save a prompt" onClose={() => setDlg(false)}
          footer={<>
            <Button variant="ghost" onClick={() => setDlg(false)}>Cancel</Button>
            <Button variant="primary" onClick={doSave}>Save</Button>
          </>}>
          <Input autoFocus placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea placeholder="Prompt body" value={body} onChange={(e) => setBody(e.target.value)} rows={4}
            style={{ background: "var(--paper-3)", border: "1px solid var(--rule)", borderRadius: 9, padding: "10px 12px", fontFamily: "var(--font-read)", fontSize: 14, color: "var(--ink)", resize: "vertical" }} />
          <Input placeholder="Tags (comma-separated)" value={tags} onChange={(e) => setTags(e.target.value)} />
        </Dialog>
      )}
    </div>
  );
}
