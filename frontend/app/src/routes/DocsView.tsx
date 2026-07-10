import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listDocuments, uploadDocument, deleteDocument, searchDocuments, listMembers } from "@/lib/api";
import type { DocumentSearchHit, WorkspaceDocument } from "@/lib/types";
import { can } from "@/lib/rbac";
import { useSession, useEffectiveRole } from "@/store/session";
import { formatBytes } from "@/lib/format";
import { useToast } from "@/components/common/Toast";
import { Button } from "@/components/common/Button";
import { Dialog } from "@/components/common/Dialog";
import { Spinner, EmptyState } from "@/components/common/Feedback";
import s from "./docs.module.css";

// The plate shows the file's kind at a glance ("md", "pdf", "py") — a shelf
// you can scan. Falls back to the knowledge-base mark for odd names.
function extOf(filename: string): string {
  const ext = filename.includes(".") ? filename.split(".").pop()! : "";
  return ext && ext.length <= 4 ? ext : "⌘";
}

/** The workspace knowledge base (AI-LANE-CONTRACTS §2.3). Documents uploaded
 * here ground chat replies automatically — with citation chips — whenever a
 * question clears the relevance gate. There is no per-conversation attach. */
export function DocsView() {
  const { wid } = useParams();
  const qc = useQueryClient();
  const { push } = useToast();
  const user = useSession((st) => st.user);
  const role = useEffectiveRole();
  const canWrite = can(role, "document.write");

  const fileInput = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [confirmDoc, setConfirmDoc] = useState<WorkspaceDocument | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DocumentSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["documents", wid],
    queryFn: () => listDocuments(wid!),
    enabled: !!wid,
    // Ingestion runs server-side in the background: keep polling while any
    // document is still processing so chips flip to ready/error on their own.
    refetchInterval: (q) =>
      q.state.data?.items.some((d) => d.status === "processing") ? 1500 : false,
  });
  const docs = data?.items ?? [];

  const { data: members } = useQuery({
    queryKey: ["members", wid],
    queryFn: () => listMembers(wid!),
    enabled: !!wid,
  });
  const emailOf = (id: string) =>
    id === user?.id ? "you" : members?.find((m) => m.user_id === id)?.email ?? "teammate";

  async function doUpload(files: FileList | File[]) {
    if (!wid) return;
    for (const file of Array.from(files)) {
      try {
        await uploadDocument(wid, file);
        push(`Ingesting ${file.name}…`);
      } catch (e: any) {
        push(e?.message ?? `Upload of ${file.name} failed`, "error");
      }
    }
    qc.invalidateQueries({ queryKey: ["documents", wid] });
  }

  async function doDelete(doc: WorkspaceDocument) {
    if (!wid) return;
    try {
      await deleteDocument(wid, doc.id);
      push(`${doc.filename} removed — grounding stops citing it on the next send`);
      qc.invalidateQueries({ queryKey: ["documents", wid] });
    } catch (e: any) { push(e?.message ?? "Delete failed", "error"); }
  }

  async function doSearch() {
    if (!wid || !query.trim()) { setHits(null); return; }
    setSearching(true);
    try {
      const r = await searchDocuments(wid, query.trim());
      setHits(r.items);
    } catch (e: any) { push(e?.message ?? "Search failed", "error"); }
    setSearching(false);
  }

  return (
    <div className={`${s.scroll} folio`}>
      <div className={s.inner}>
        <div className={s.headRow}>
          <div>
            <div className="serif-d" style={{ fontSize: 32 }}>Knowledge Base</div>
            <div style={{ color: "var(--ink-3)", marginTop: 8, fontSize: 13.5 }}>
              The workspace's source documents. When a question touches one, the reply grounds
              itself on it — cited, with ⌘ chips. Unrelated questions leave the shelf alone.
            </div>
          </div>
          {canWrite && (
            <Button variant="primary" onClick={() => fileInput.current?.click()}>+ Upload</Button>
          )}
        </div>
        <div className="chapter-rule" aria-hidden>❦</div>

        {canWrite && (
          <>
            <input
              ref={fileInput} type="file" multiple hidden
              accept=".txt,.md,.markdown,.pdf,.py,.js,.ts,.tsx,.jsx,.json,.yaml,.yml,.toml,.css,.html,.csv,.rst"
              onChange={(e) => { if (e.target.files?.length) doUpload(e.target.files); e.target.value = ""; }}
            />
            <div
              className={`${s.drop} ${dragOver ? s.dropActive : ""}`}
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files.length) doUpload(e.dataTransfer.files); }}
            >
              <span className={s.dropGlyph}>⌘</span>
              <span style={{ fontSize: 14 }}>Drop a document here, or click to browse</span>
              <span className={s.dropHint}>txt · md · code · pdf — up to 8 MB each</span>
            </div>
          </>
        )}

        {docs.some((d) => d.status === "ready") && (
          <div className={s.search}>
            <span style={{ color: "var(--ink-faint)" }}>⌕</span>
            <input
              className={s.searchInput}
              placeholder="Search the knowledge base — the same ranking chat grounding uses"
              value={query}
              onChange={(e) => { setQuery(e.target.value); if (!e.target.value.trim()) setHits(null); }}
              onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }}
            />
            {hits !== null && (
              <Button variant="ghost" style={{ padding: "4px 10px", fontSize: 12 }}
                onClick={() => { setQuery(""); setHits(null); }}>clear</Button>
            )}
            <Button disabled={searching || !query.trim()} onClick={doSearch}>Search</Button>
          </div>
        )}

        {hits !== null && (
          <div className={s.list}>
            {hits.length === 0 ? (
              <EmptyState title="Nothing relevant">
                No chunk cleared the relevance ranking for that query — which is exactly why an
                unrelated chat question doesn't drag the knowledge base into its prompt.
              </EmptyState>
            ) : hits.map((h, i) => (
              <div key={`${h.document_id}-${h.chunk_index}-${i}`} className={s.hit}>
                <div className={s.hitHead}>
                  <span className="mono" style={{ fontSize: 12.5, color: "var(--oxblood)" }}>
                    ⌘ {h.filename} §{h.chunk_index + 1}
                  </span>
                  <span className={s.hitScoreBar} title={`relevance ${h.score.toFixed(2)}`}>
                    <span className={s.hitScoreFill} style={{ display: "block", width: `${Math.min(100, Math.round(h.score * 100))}%` }} />
                  </span>
                  <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{h.score.toFixed(2)}</span>
                </div>
                <div className={s.hitBody}>{h.content}</div>
              </div>
            ))}
          </div>
        )}

        {hits === null && (isLoading ? <Spinner /> : docs.length === 0 ? (
          <EmptyState title="The shelf is empty">
            {canWrite
              ? "Upload a spec, a paper, or notes — Helix cites them in chat whenever a question touches them."
              : "No documents yet. A Collaborator or Owner can stock the shelf."}
          </EmptyState>
        ) : (
          <div className={s.list}>
            {docs.map((d) => (
              <div key={d.id} className={s.row}>
                <div className={s.docGlyph} style={{ color: d.status === "error" ? "var(--oxblood)" : "var(--gilt-1)" }}>
                  {d.status === "error" ? "✕" : extOf(d.filename)}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className={s.docName}>{d.filename}</div>
                  {d.status === "error" ? (
                    <div className={s.docError}>{d.error || "ingestion failed"}</div>
                  ) : (
                    <div className={s.docMeta}>
                      {d.status === "ready" && <span>{d.chunk_count} chunks</span>}
                      {d.status === "ready" && <span>{d.text_chars.toLocaleString()} chars</span>}
                      <span>{formatBytes(d.size_bytes)}</span>
                      <span>by {emailOf(d.author_id)}</span>
                      <span>{new Date(d.created_at).toLocaleDateString()}</span>
                    </div>
                  )}
                </div>
                <span className={`${s.status} ${d.status === "ready" ? s.statusReady : d.status === "processing" ? s.statusProcessing : s.statusError}`}>
                  {d.status === "ready" ? "✓ ready" : d.status === "processing" ? "⟳ processing" : "✕ error"}
                </span>
                {(d.author_id === user?.id || role === "owner") && canWrite && (
                  <button className={s.delete} title="Delete document" onClick={() => setConfirmDoc(d)}>✕</button>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>

      {confirmDoc && (
        <Dialog title="Remove from the knowledge base?" onClose={() => setConfirmDoc(null)}
          footer={<>
            <Button variant="ghost" onClick={() => setConfirmDoc(null)}>Cancel</Button>
            <Button variant="primary" onClick={() => { doDelete(confirmDoc); setConfirmDoc(null); }}>Delete</Button>
          </>}>
          <div style={{ fontSize: 13.5, color: "var(--ink-2)", lineHeight: 1.55 }}>
            <span className="mono" style={{ color: "var(--oxblood)" }}>⌘ {confirmDoc.filename}</span> and its
            chunks are removed for the whole workspace. Replies stop citing it on the next send.
          </div>
        </Dialog>
      )}
    </div>
  );
}
