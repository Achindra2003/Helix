import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listPrompts, savePrompt, updatePrompt, deletePrompt } from "@/lib/api";
import type { Prompt } from "@/lib/types";
import { onRoomEvent } from "@/lib/realtime";
import { usePendingInsert } from "@/store/insert";
import { useSession, useEffectiveRole } from "@/store/session";
import { can } from "@/lib/rbac";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Dialog } from "@/components/common/Dialog";
import { Input } from "@/components/common/Input";
import { Spinner, EmptyState } from "@/components/common/Feedback";
import { ACTION, ORNAMENT, PLACE } from "@/lib/glyphs";
import s from "./library.module.css";

// Purely decorative: it alternates down the list so the cards read as a set of
// entries rather than a stack of boxes. Six marks used to rotate here, four of
// them (◆ ● ❖ ◈) marks that carry meaning elsewhere in the product — an owner,
// a live run, a status. Ornament that borrows a meaningful mark teaches the
// reader that the mark means nothing, so it is the two fleurons and nothing
// else. See lib/glyphs.ts.
const ORNAMENTS = [ORNAMENT.bud, ORNAMENT.leaf];

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
  const user = useSession((st) => st.user);
  const role = useEffectiveRole();
  const canWrite = can(role, "prompt.write");
  const request = usePendingInsert((st) => st.request);

  const [search, setSearch] = useState("");
  const [dlg, setDlg] = useState(false);
  const [editId, setEditId] = useState<string | null>(null); // dialog edits instead of creating
  const [confirmDel, setConfirmDel] = useState<Prompt | null>(null);
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

  // Live fan-out: a teammate saving/editing/deleting a prompt refreshes in place.
  useEffect(
    () =>
      onRoomEvent((ev) => {
        if (ev.kind === "prompt.saved" || ev.kind === "prompt.deleted") {
          qc.invalidateQueries({ queryKey: ["prompts", wid] });
        }
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
    const tagList = tags.split(",").map((t) => t.trim()).filter(Boolean);
    try {
      if (editId) await updatePrompt(editId, title.trim(), body.trim(), tagList);
      else await savePrompt(wid, title.trim(), body.trim(), tagList);
      await qc.invalidateQueries({ queryKey: ["prompts", wid] });
      setDlg(false); setEditId(null); setTitle(""); setBody(""); setTags("");
      push(editId ? "Prompt updated" : "Prompt saved");
    } catch (e: any) { push(e?.message ?? "Save failed", "error"); }
  }

  function openEdit(p: Prompt) {
    setEditId(p.id);
    setTitle(p.title); setBody(p.body); setTags((p.tags ?? []).join(", "));
    setDlg(true);
  }

  async function doDelete() {
    if (!confirmDel) return;
    try {
      await deletePrompt(confirmDel.id);
      await qc.invalidateQueries({ queryKey: ["prompts", wid] });
      push("Prompt deleted");
      setConfirmDel(null);
    } catch (e: any) { push(e?.message ?? "Delete failed", "error"); }
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
            <div style={{ color: "var(--ink-3)", marginTop: 8, fontSize: 13 }}>
              The shared record of what works — tagged, searchable, reusable across every conversation.
            </div>
          </div>
          {canWrite && <Button variant="primary" onClick={() => setDlg(true)}>+ Save prompt</Button>}
        </div>
        <div className="chapter-rule" aria-hidden>❦</div>

        <div className={s.search}>
          <span style={{ color: "var(--oxblood)", fontSize: 15 }} aria-hidden>{PLACE.find}</span>
          <input className={s.searchInput} aria-label="Search saved prompts"
            placeholder="Search title, body, or tags…" value={search} onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") setSearch(""); }} />
          {/* Says what the number counts. "4 prompts" while a search was active
              read as the size of the library, so a filter that hid most of it
              looked like a library that had lost most of it. */}
          <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>
            {search ? `${filtered.length} of ${prompts.length}` : `${prompts.length} prompts`}
          </span>
          {search && (
            <button className={`icon-act ${s.cardAct}`} title="Clear the search (Esc)"
              aria-label="Clear the search" onClick={() => setSearch("")}>{ACTION.remove}</button>
          )}
        </div>

        {isLoading || seeding ? <Spinner /> : filtered.length === 0 ? (
          /* Two different nothings. The library being empty and the search
             matching nothing were both "An empty library", which told someone
             hunting for a prompt that their team's pages were gone. */
          search ? (
            <EmptyState title="Nothing matches that">
              No prompt here mentions “{search}”.{" "}
              <button className={s.linkAct} onClick={() => setSearch("")}>Clear the search</button>{" "}
              to see all {prompts.length}.
            </EmptyState>
          ) : (
            <EmptyState title="An empty library">Save a winning prompt — a page kept here can be inserted into any thread, by anyone on the team.</EmptyState>
          )
        ) : (
          <div className={s.grid}>
            {filtered.map((p, i) => (
              <div key={p.id} className={s.card} style={{ animationDelay: `${Math.min(i, 10) * 45}ms` }}>
                <div className={s.cardHead}>
                  <span className={s.sigil} aria-hidden>{ORNAMENTS[i % ORNAMENTS.length]}</span>
                  <div className={s.cardTitle}>{p.title}</div>
                </div>
                <div className={s.cardBody}>"{p.body}"</div>
                <div className={s.cardFoot}>
                  {/* A tag you can read but not act on is a label; the search
                      already matches tags, so the tag is the search. */}
                  {(p.tags ?? []).map((t) => (
                    <button key={t} className={s.tag} onClick={() => setSearch(search === t ? "" : t)}
                      aria-pressed={search === t}
                      title={search === t ? `Stop filtering by ${t}` : `Show only prompts tagged ${t}`}>
                      {t}
                    </button>
                  ))}
                  <div style={{ flex: 1 }} />
                  {/* canWrite as well as authorship: a demoted Observer still
                      authored these, and without the role check their own
                      prompts kept edit/delete buttons that the server now
                      refuses. */}
                  {canWrite && (p.author_id === user?.id || role === "owner") && (
                    <>
                      {/* aria-label as well as title: the button's own text is
                          a glyph, and text content wins the accessible name. */}
                      <button className={`icon-act ${s.cardAct}`} title="Edit prompt"
                        aria-label={`Edit "${p.title}"`} onClick={() => openEdit(p)}>{ACTION.edit}</button>
                      <button className={`icon-act ${s.cardAct} ${s.cardActDanger}`} title="Delete prompt"
                        aria-label={`Delete "${p.title}"`} onClick={() => setConfirmDel(p)}>{ACTION.remove}</button>
                    </>
                  )}
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
        <Dialog title={editId ? "Edit prompt" : "Save a prompt"}
          onClose={() => { setDlg(false); setEditId(null); setTitle(""); setBody(""); setTags(""); }}
          footer={<>
            <Button variant="ghost" onClick={() => { setDlg(false); setEditId(null); setTitle(""); setBody(""); setTags(""); }}>Cancel</Button>
            <Button variant="primary" onClick={doSave}>{editId ? "Update" : "Save"}</Button>
          </>}>
          <Input autoFocus placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea placeholder="Prompt body" value={body} onChange={(e) => setBody(e.target.value)} rows={4}
            style={{ background: "var(--paper-3)", border: "1px solid var(--rule)", borderRadius: 9, padding: "10px 12px", fontFamily: "var(--font-read)", fontSize: 14, color: "var(--ink)", resize: "vertical" }} />
          <Input placeholder="Tags (comma-separated)" value={tags} onChange={(e) => setTags(e.target.value)} />
        </Dialog>
      )}
      {confirmDel && (
        <Dialog title={`Delete "${confirmDel.title}"?`} onClose={() => setConfirmDel(null)}
          footer={<>
            <Button variant="ghost" onClick={() => setConfirmDel(null)}>Cancel</Button>
            <Button variant="oxblood" onClick={doDelete}>Delete</Button>
          </>}>
          <div style={{ fontSize: 13, color: "var(--ink-2)" }}>
            It disappears from the whole team's library. Turns already inserted from it stay in
            their conversations.
          </div>
        </Dialog>
      )}
    </div>
  );
}
